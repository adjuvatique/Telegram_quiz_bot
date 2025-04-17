# bot.py
import os
import json
import logging

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# Логирование, чтобы видеть события в консоли
logging.basicConfig(
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
    level=logging.INFO,
)

# Получаем токен из переменной окружения
TOKEN = os.getenv("TG_QUIZ_TOKEN")

# Загружаем вопросы
with open("questions.json", encoding="utf-8") as f:
    QUESTIONS = json.load(f)

# Состояние пользователей
user_state = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Напиши /quiz, чтобы начать викторину.")

async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_state[chat_id] = {"index": 0, "score": 0}
    await send_question(chat_id, context)

async def send_question(chat_id, context):
    state = user_state[chat_id]
    q = QUESTIONS[state["index"]]
    keyboard = ReplyKeyboardMarkup([[opt] for opt in q["options"]], one_time_keyboard=True)
    await context.bot.send_message(chat_id, f"Вопрос {state['index']+1}: {q['question']}", reply_markup=keyboard)

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    state = user_state.get(chat_id)
    if not state:
        return await update.message.reply_text("Сначала напиши /quiz.")
    q = QUESTIONS[state["index"]]
    if update.message.text == q["answer"]:
        state["score"] += 1
        await update.message.reply_text("✅ Правильно!")
    else:
        await update.message.reply_text(f"❌ Неверно. Правильный ответ: {q['answer']}")
    state["index"] += 1
    if state["index"] < len(QUESTIONS):
        await send_question(chat_id, context)
    else:
        await update.message.reply_text(f"Игра окончена! Твой счёт: {state['score']}/{len(QUESTIONS)}")
        user_state.pop(chat_id)

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("quiz", quiz))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_answer))
    print("📡 Quiz-бот запущен. Ожидаю сообщений…")
    app.run_polling()

if __name__ == "__main__":
    main()
