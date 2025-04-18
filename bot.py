import os
import pathlib
import logging
import json
import random
import asyncio
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    filename='quiz_bot.log',
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Загрузка переменных из .env
dotenv_path = pathlib.Path(__file__).parent / '.env'
load_dotenv(dotenv_path=dotenv_path, override=True)

# Чтение переменных
SHEET_ID = os.getenv('GS_SHEET_ID')
TOKEN = os.getenv('TG_QUIZ_TOKEN')
RATING_FILE = 'rating.json'

# Категории для вопросов
CATEGORIES = [
    "🎲 Случайный микс",
    "Типы тестирования",
    "Техники дизайна тестов",
    "Инструменты и фреймворки",
    "DevOps и контейнеризация",
    "API‑тестирование и веб‑сервисы",
    "Производительность и нагрузка",
    "Безопасность (Security Testing)",
    "Доступность и юзабилити",
    "Мобильное тестирование",
    "Совместимость (Compatibility)",
    "Процессы и стандарты",
    "Программирование и скрипты",
    "Мягкие навыки (Soft Skills)"
]
QUESTIONS: dict = {}

# Загрузка вопросов из Google Sheets
def load_questions_from_sheets() -> dict:
    scope = ['https://www.googleapis.com/auth/spreadsheets.readonly']
    creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SHEET_ID).sheet1
    rows = sheet.get_all_records()
    questions = {cat: [] for cat in CATEGORIES if cat != "🎲 Случайный микс"}
    for row in rows:
        cat = str(row.get('category', '')).strip()
        if cat in questions:
            questions[cat].append({
                'question': str(row.get('question', '')).strip(),
                'options': [str(row.get(f'option{i}', '')).strip() for i in range(1, 5)],
                'answer': str(row.get('answer', '')).strip(),
                'difficulty': str(row.get('difficulty', 'Средний')).strip()
            })
    return questions

# Асинхронная инициализация вопросов
async def init_questions():
    global QUESTIONS
    try:
        QUESTIONS = await asyncio.to_thread(load_questions_from_sheets)
        logging.info(f"Загружено вопросов: {sum(len(v) for v in QUESTIONS.values())}")
    except Exception as e:
        logging.error(f"Ошибка загрузки вопросов: {e}")
        QUESTIONS = {cat: [] for cat in CATEGORIES if cat != "🎲 Случайный микс"}

# Время на ответ в зависимости от сложности
def get_timeout(difficulty: str) -> int:
    return {"Лёгкий": 10, "Средний": 20, "Сложный": 30}.get(difficulty, 20)

# Отправка одного вопроса по chat_id
async def send_question_by_chat_id(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    data = context.chat_data
    qlist = data.get('questions', [])
    idx = data.get('index', 0)

    if idx >= len(qlist) or not qlist:
        return await end_quiz_by_chat_id(chat_id, context)

    q = qlist[idx]
    data['current_q'] = q
    timeout = get_timeout(q.get('difficulty', 'Средний'))
    job = context.job_queue.run_once(
        time_up,
        timeout,
        chat_id=chat_id,
        name=f"timeup_{chat_id}"
    )
    data['job'] = job

    kb = ReplyKeyboardMarkup([[opt] for opt in q['options']], one_time_keyboard=True, resize_keyboard=True)
    text = (f"❓ Вопрос {idx+1}/{len(qlist)}\n"
            f"{q['question']}\n"
            f"({q.get('difficulty')})")
    await context.bot.send_message(chat_id, text, reply_markup=kb)

# Завершение квиза: подсчёт результатов и обновление рейтинга
async def end_quiz_by_chat_id(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    data = context.chat_data
    score = data.get('score', 0)
    total = len(data.get('questions', []))
    percent = (score / total * 100) if total else 0
    medal = ("🏅 Великолепно!" if percent >= 90 else
             "👏 Отлично!" if percent >= 70 else
             "👍 Хорошо!" if percent >= 50 else
             "💡 Учиться есть чему!" if percent >= 30 else
             "😅 Не отчаивайся!")
    msg = f"🧾 Результат: {score}/{total}\n{medal}"

    # Обновляем рейтинг
    rating = context.bot_data.setdefault('rating', {})
    chat = await context.bot.get_chat(chat_id)
    name = chat.first_name or str(chat_id)
    rating[name] = rating.get(name, 0) + score
    with open(RATING_FILE, 'w', encoding='utf-8') as f:
        json.dump({k: int(v) for k, v in rating.items()}, f, ensure_ascii=False, indent=2)
    logging.info(f"Пользователь {name}: {score}/{total}, новый рейтинг: {rating[name]}")

    # Отображаем топ‑5
    top = sorted(rating.items(), key=lambda x: x[1], reverse=True)[:5]
    lb = "\n".join([f"{i+1}. {u} — {pts}" for i, (u, pts) in enumerate(top)])
    kb = ReplyKeyboardMarkup([['▶️ Играть', '🏆 Рейтинг']], resize_keyboard=True)
    await context.bot.send_message(chat_id, msg + f"\n\n🏆 Рейтинг:\n{lb}", reply_markup=kb)

    context.chat_data.clear()

# Обработчик таймаута по вопросу
async def time_up(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id
    q = context.chat_data.get('current_q')
    if q:
        await context.bot.send_message(chat_id, f"⏰ Время вышло! Правильный ответ: {q['answer']}")
        context.chat_data['index'] += 1
        await send_question_by_chat_id(chat_id, context)

# Команда /start — приветствие и инструкции
async def start(update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or 'друг'
    text = (
        f"👋 Привет, {name}! Я — бот‑квиз по тестированию ПО."
        "\n\n⚙️ Правила:"
        "\n  • На каждый вопрос даётся ограниченное время:"
        "\n    – Лёгкий: 10 сек;"
        "\n    – Средний: 20 сек;"
        "\n    – Сложный: 30 сек."
        "\n  • Если не успел — вопрос пропускается как неверный."
        "\n\n▶️ Нажми «Играть» или /quiz, чтобы начать."
        "\n🏆 Нажми «Рейтинг» или /rating, чтобы посмотреть лидеров."
        "\n🛑 /stop — отмена текущего квиза."
        "\nℹ️ /help — список команд."
    )
    kb = ReplyKeyboardMarkup([['▶️ Играть', '🏆 Рейтинг']], resize_keyboard=True)
    await update.message.reply_text(text, reply_markup=kb)

# Команда /help — справка по командам
async def help_command(update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Команды:"
        "\n/start — перейти в главное меню"
        "\n/quiz — начать новый квиз"
        "\n/rating — показать топ‑рейтинги"
        "\n/stop — остановить текущий квиз"
        "\n/help — показать эту справку"
    )
    await update.message.reply_text(text)

# Запуск квиза: выбор категории
async def quiz(update, context: ContextTypes.DEFAULT_TYPE):
    context.chat_data.clear()
    kb = ReplyKeyboardMarkup([[cat] for cat in CATEGORIES], one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text('Выбери категорию:', reply_markup=kb)

# Обработка выбора категории
async def handle_category(update, context: ContextTypes.DEFAULT_TYPE):
    cat = update.message.text
    if cat not in CATEGORIES:
        return await update.message.reply_text('Пожалуйста, выбери категорию кнопкой.')
    context.chat_data['category'] = cat
    if cat == '🎲 Случайный микс':
        all_q = [q for lst in QUESTIONS.values() for q in lst]
        random.shuffle(all_q)
        mix_size = random.randint(8, 15)
        context.chat_data.update({'questions': all_q[:mix_size], 'difficulty': 'микс', 'index': 0, 'score': 0})
        return await send_question_by_chat_id(update.effective_chat.id, context)
    kb = ReplyKeyboardMarkup([['Лёгкий'], ['Средний'], ['Сложный']], one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text('Выбери сложность:', reply_markup=kb)

# Обработка выбора сложности
async def handle_difficulty(update, context: ContextTypes.DEFAULT_TYPE):
    diff = update.message.text
    if diff not in ['Лёгкий', 'Средний', 'Сложный']:
        return await update.message.reply_text('Пожалуйста, нажми одну из кнопок.')
    context.chat_data['difficulty'] = diff
    cat = context.chat_data['category']
    context.chat_data.update({
        'questions': [q for q in QUESTIONS.get(cat, []) if q['difficulty'] == diff],
        'index': 0,
        'score': 0
    })
    await send_question_by_chat_id(update.effective_chat.id, context)

# Обработка ответа пользователя
async def handle_answer(update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    data = context.chat_data
    job = data.pop('job', None)
    if job:
        job.schedule_removal()
    q = data.get('current_q')
    if q and update.message.text == q['answer']:
        data['score'] += 1
        await update.message.reply_text('✅ Верно!')
    else:
        ans = q['answer'] if q else '—'
        await update.message.reply_text(f'❌ Неверно. Правильный ответ: {ans}')
    data['index'] += 1
    await send_question_by_chat_id(chat_id, context)

# Показ текущего рейтинга
async def show_rating(update, context: ContextTypes.DEFAULT_TYPE):
    rating = context.bot_data.get('rating', {})
    if not rating:
        return await update.message.reply_text('Пока никто не играл.')
    top = sorted(rating.items(), key=lambda x: x[1], reverse=True)[:10]
    lb = "\n".join([f"{i+1}. {u} — {pts}" for i,(u,pts) in enumerate(top)])
    await update.message.reply_text(f"🏆 Рейтинг:\n{lb}")

# Остановка квиза
async def stop_quiz(update, context: ContextTypes.DEFAULT_TYPE):
    context.chat_data.clear()
    await update.message.reply_text('Сессия прервана.', reply_markup=ReplyKeyboardRemove())

# Общий хендлер для всех текстовых сообщений
async def handle_message(update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text in ['▶️ Играть', 'Играть']:
        return await quiz(update, context)
    if text in ['🏆 Рейтинг', 'Рейтинг']:
        return await show_rating(update, context)
    if 'category' not in context.chat_data:
        return await handle_category(update, context)
    if 'difficulty' not in context.chat_data:
        return await handle_difficulty(update, context)
    return await handle_answer(update, context)

def main() -> None:
    app = ApplicationBuilder().token(TOKEN).build()

    # Загрузка и приведение рейтинга к целым числам
    if os.path.exists(RATING_FILE):
        with open(RATING_FILE, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        rating = {}
        for u, v in raw.items():
            try:
                rating[u] = int(v)
            except:
                rating[u] = 0
        app.bot_data['rating'] = rating
    else:
        app.bot_data['rating'] = {}

    # Регистрация хендлеров
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CommandHandler('quiz', quiz))
    app.add_handler(CommandHandler('rating', show_rating))
    app.add_handler(CommandHandler('stop', stop_quiz))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Инициализация вопросов и запуск бота
    asyncio.set_event_loop(asyncio.new_event_loop())
    asyncio.get_event_loop().run_until_complete(init_questions())
    print('📡 Бот запущен. Ожидаю игроков...')
    app.run_polling()

if __name__ == '__main__':
    main()
