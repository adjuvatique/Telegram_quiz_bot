import os
import json
import logging

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
    level=logging.INFO,
)

# Токен Telegram из переменной окружения
TOKEN = os.getenv("TG_QUIZ_TOKEN")

# Основные категории викторины
CATEGORIES = [
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

# Уровни сложности
DIFFICULTIES = ["Легкий", "Средний", "Сложный"]

# Папка с вопросами
QUESTIONS_DIR = 'questions'
# Файл для хранения рейтинга
SCORE_FILE = 'scores.json'

# Загрузка вопросов из JSON-файлов
QUESTIONS = {}
for category in CATEGORIES:
    slug = category.lower().replace(' ', '_').replace('(', '').replace(')', '').replace('‑', '-')
    path = os.path.join(QUESTIONS_DIR, slug + '.json')
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
            QUESTIONS[category] = data if isinstance(data, list) else []
    except FileNotFoundError:
        logging.info(f"Файл с вопросами не найден: {path}")
        QUESTIONS[category] = []
    except json.JSONDecodeError:
        logging.warning(f"Неверный JSON в файле: {path}")
        QUESTIONS[category] = []
    except Exception as e:
        logging.error(f"Ошибка загрузки {path}: {e}")
        QUESTIONS[category] = []

# Состояние пользователей
user_state = {}

# Функции для работы с рейтингом

def load_scores():
    try:
        with open(SCORE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_scores(scores):
    try:
        with open(SCORE_FILE, 'w', encoding='utf-8') as f:
            json.dump(scores, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Ошибка сохранения рейтинга: {e}")

# Команды
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 Привет! Я — Quiz‑бот для тестировщиков."
        "\nИспользуй /quiz, чтобы начать викторину."  
        "\nСправка — /help, рейтинг — /leaderboard"
    )
    await update.message.reply_text(text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📋 *Команды:*\n"
        "/start — приветствие\n"
        "/help — это сообщение\n"
        "/quiz — начать викторину\n"
        "/leaderboard — топ участников"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    scores = load_scores()
    if not scores:
        await update.message.reply_text("Рейтинг пока пуст. Станьте первым, кто сыграет!")
        return
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    msg = "🏆 *Топ участников:*\n"
    for i, (user, pts) in enumerate(sorted_scores[:10], 1):
        msg += f"{i}. {user}: {pts} очков\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_state[chat_id] = {
        'difficulty': None,
        'category': None,
        'questions': [],
        'index': 0,
        'score': 0
    }
    keyboard = ReplyKeyboardMarkup(
        [[d] for d in DIFFICULTIES],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await update.message.reply_text('Выберите уровень сложности:', reply_markup=keyboard)

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    username = update.effective_user.full_name
    text = update.message.text.strip()

    # Главное меню кнопок
    if text == '▶️ Новая викторина':
        return await quiz(update, context)
    if text == '📋 Категории':
        keyboard = ReplyKeyboardMarkup(
            [[c] for c in CATEGORIES],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        return await update.message.reply_text('Выберите категорию викторины:', reply_markup=keyboard)
    if text == '⭐️ Рейтинг':
        return await leaderboard(update, context)
    if text == '❓ Справка':
        return await help_command(update, context)

    state = user_state.get(chat_id)
    if not state:
        await update.message.reply_text('Напишите /quiz, чтобы начать викторину.')
        return

    # Выбор сложности
    if state['difficulty'] is None:
        if text not in DIFFICULTIES:
            await update.message.reply_text(f'❌ Неправильный уровень: {text}')
            return
        state['difficulty'] = text
        keyboard = ReplyKeyboardMarkup(
            [[c] for c in CATEGORIES],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await update.message.reply_text('Выберите категорию викторины:', reply_markup=keyboard)
        return

    # Выбор категории
    if state['category'] is None:
        if text not in CATEGORIES:
            await update.message.reply_text(f'❌ Категория {text} не найдена.')
            return
        state['category'] = text
        all_q = QUESTIONS.get(text, [])
        # Фильтрация по difficulty
        filtered = [q for q in all_q if q.get('difficulty') == state['difficulty']] if any('difficulty' in q for q in all_q) else all_q
        state['questions'] = filtered
        if not filtered:
            await update.message.reply_text('❌ В этой категории нет вопросов для выбранного уровня.')
            return
        await send_question(update, context)
        return

    # Обработка ответа
    q_list = state['questions']
    idx = state['index']
    current = q_list[idx]
    if text == current['answer']:
        state['score'] += 1
        await update.message.reply_text('✅ Правильно!')
    else:
        await update.message.reply_text(f'❌ Неверно. Правильный ответ: {current["answer"]}')
    state['index'] += 1
    if state['index'] < len(q_list):
        await send_question(update, context)
        return

    # Конец викторины: результаты и меню
    score = state['score']
    total = len(q_list)
    percent = score / total
    # Обновление рейтинга
    scores = load_scores()
    scores[username] = scores.get(username, 0) + score
    save_scores(scores)

    if percent >= 0.8:
        msg = f"🎉 Отлично, {username}! Вы набрали {score}/{total} ({percent:.0%}). Так держать!"
    elif percent >= 0.5:
        msg = f"👍 Неплохо, {username}! Вы набрали {score}/{total} ({percent:.0%}). Почти идеально, попробуйте ещё раз!"
    else:
        msg = f"💪 Не расстраивайтесь, {username}! Вы набрали {score}/{total} ({percent:.0%}). Продолжайте практиковаться!"

    keyboard = ReplyKeyboardMarkup(
        [
            ['▶️ Новая викторина'],
            ['📋 Категории', '⭐️ Рейтинг'],
            ['❓ Справка']
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await update.message.reply_text(
        f"{msg}\n\nЧто дальше?",
        reply_markup=keyboard
    )
    user_state.pop(chat_id)

async def send_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    state = user_state.get(chat_id)
    if not state or not state.get('questions'):
        return
    q = state['questions'][state['index']]
    keyboard = ReplyKeyboardMarkup(
        [[opt] for opt in q['options']],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    text = (
        f"📋 *{state['category']}* | {state['difficulty']}\n"
        f"Вопрос {state['index']+1}/{len(state['questions'])}: {q['question']}"
    )
    await context.bot.send_message(
        chat_id,
        text=text,
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# Запуск бота
if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CommandHandler('leaderboard', leaderboard))
    app.add_handler(CommandHandler('quiz', quiz))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    print('📡 Quiz-бот запущен. Ожидаю сообщений…')
    app.run_polling()
