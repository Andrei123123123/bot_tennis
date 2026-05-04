import os
import asyncio
import signal
import logging
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.request import HTTPXRequest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("Переменная TELEGRAM_BOT_TOKEN не найдена. Добавь её в настройках окружения.")
ADMIN_ID = 5495812267

REPLIES_FILE = "pending_replies.json"

def load_replies() -> dict[int, tuple[int, str]]:
    if os.path.exists(REPLIES_FILE):
        try:
            with open(REPLIES_FILE, "r") as f:
                data = json.load(f)
                return {int(k): tuple(v) for k, v in data.items()}
        except Exception:
            pass
    return {}

def save_replies(data: dict[int, tuple[int, str]]):
    with open(REPLIES_FILE, "w") as f:
        json.dump({str(k): list(v) for k, v in data.items()}, f)

# Хранит: {message_id пересланного сообщения → (chat_id, имя пользователя)}
pending_replies: dict[int, tuple[int, str]] = load_replies()

# ───── МЕНЮ ─────
def main_menu():
    keyboard = [
        [InlineKeyboardButton("🎾 Программа и цены", callback_data="programa")],
        [InlineKeyboardButton("🛂 Виза через академию", callback_data="viza")],
        [InlineKeyboardButton("📅 Забронировать место", callback_data="booking")],
        [InlineKeyboardButton("💬 Задать вопрос", callback_data="question")],
    ]
    return InlineKeyboardMarkup(keyboard)

# ───── СТАРТ ─────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name
    await update.message.reply_text(
        f"Привет, {name}!\n\n"
        "Теннисный и падел кемп на Тенерифе — 14–20 сентября 2026.\n\n"
        "7 дней на Канарских островах:\n"
        "— Вилла с бассейном и личным поваром\n"
        "— 6 тренировок в Tenerife Tennis Academy\n"
        "— Русскоязычный тренер\n"
        "— Теннис или падел — выбираешь каждый день\n"
        "— Яхта, Тейде, Маска, сёрфинг, банкет в замке\n"
        "— Шенген по приглашению от академии\n"
        "— Всё включено — берёшь только паспорт\n\n"
        "Группа — 12 человек. Выбери что тебя интересует:",
        reply_markup=main_menu()
    )

# ───── КНОПКИ ─────
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    back = [[InlineKeyboardButton("← Назад", callback_data="back")]]

    if query.data == "programa":
        text = (
            "🎾 <b>Программа и цены</b>\n\n"
            "7 дней, 6 тренировок — теннис или падел на выбор каждый день.\n"
            "Тренировки: 16:00–18:00 в Tenerife Tennis Academy.\n\n"
            "<b>Утром — активности:</b>\n"
            "— Яхта, купание, дельфины\n"
            "— Вулкан Тейде, 3718 м\n"
            "— Ущелье Маска, хайкинг\n"
            "— Сёрфинг с инструктором\n"
            "— Банкет в замке Сан-Мигель\n\n"
            "<b>Цены:</b>\n"
            "— Кемп: 110 000 ₽\n"
            "— Вилла: 50 000 ₽\n"
            "— Авиа: ~90 000 ₽ (помогаем подобрать)\n"
            "— Виза: ~20 000 ₽ (оформляем через партнёра)\n\n"
            "Полный пакет: ~270 000 ₽"
        )

    elif query.data == "viza":
        text = (
            "🛂 <b>Виза</b>\n\n"
            "Тенерифе — Испания, нужен шенген.\n\n"
            "Оформляем через спортивное приглашение от Tenerife Tennis Academy — "
            "это официальный документ, который значительно повышает шансы на одобрение.\n\n"
            "<b>Всем занимается партнёр ВизаGO:</b>\n"
            "— Приглашение от академии\n"
            "— Сбор документов\n"
            "— Запись в консульство\n"
            "— 500+ виз, 97% одобрение\n\n"
            "Стоимость: ~20 000 ₽\n"
            "Срок рассмотрения: 2–4 недели\n\n"
            "Бронируй минимум за 6 недель до вылета."
        )

    elif query.data == "booking":
        text = (
            "📅 <b>Забронировать место</b>\n\n"
            "Группа — 12 человек. Места фиксируются депозитом.\n\n"
            "<b>Как это работает:</b>\n"
            "1. Пишешь @oceaninthesky\n"
            "2. Отвечаем на все вопросы\n"
            "3. Вносишь депозит 33 000 ₽ — место твоё\n"
            "4. Остаток — двумя платежами до сентября\n\n"
            "Перелёт и визу помогаем оформить отдельно.\n\n"
            "👉 @oceaninthesky"
        )

    elif query.data == "question":
        text = (
            "💬 <b>Задать вопрос</b>\n\n"
            "Напиши свой вопрос прямо здесь — "
            "организатор получит его и ответит лично.\n\n"
            "Или сразу в личку: @oceaninthesky"
        )

    elif query.data == "back":
        await query.edit_message_text(
            "Выбери что тебя интересует:",
            reply_markup=main_menu()
        )
        return

    await query.edit_message_text(
        text=text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(back)
    )

# ───── ВХОДЯЩИЕ СООБЩЕНИЯ → АДМИНУ ─────
async def forward_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text

    full_name = f"{user.first_name} {user.last_name or ''}".strip()
    username_str = f"@{user.username}" if user.username else "—"

    sent = await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            f"┌ 📩 <b>Вопрос от: {full_name}</b> ({username_str})\n"
            f"└ 🆔 <code>{user.id}</code>\n\n"
            f"💬 {text}\n\n"
            f"⬆️ <b>Ответь на это сообщение</b> — и ответ уйдёт именно {full_name}."
        ),
        parse_mode="HTML"
    )

    # Запоминаем: пересланное сообщение → (chat_id, имя)
    pending_replies[sent.message_id] = (user.id, full_name)
    save_replies(pending_replies)

    await update.message.reply_text(
        "Получил! Отвечу совсем скоро.\n\n"
        "Или напрямую: @oceaninthesky",
        reply_markup=main_menu()
    )

# ───── ЛЮБОЕ СООБЩЕНИЕ ОТ АДМИНА (для диагностики) ─────
async def admin_any_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.reply_to_message:
        replied_id = msg.reply_to_message.message_id
        entry = pending_replies.get(replied_id)
        logging.info(f"Админ ответил на msg_id={replied_id}. Найдено в pending_replies: {entry}. Всего записей: {len(pending_replies)}")

        if not entry:
            await msg.reply_text(
                f"⚠️ Не нашёл пользователя для этого сообщения.\n"
                f"Записей в памяти: {len(pending_replies)}\n"
                f"ID сообщения на которое ты ответил: {replied_id}\n\n"
                f"Попроси пользователя написать снова и ответь на новое сообщение."
            )
            return

        user_chat_id, user_name = entry
        await context.bot.send_message(
            chat_id=user_chat_id,
            text=f"💬 <b>Ответ организатора:</b>\n\n{msg.text}",
            parse_mode="HTML",
            reply_markup=main_menu()
        )
        await msg.reply_text(f"✅ Ответ отправлен → <b>{user_name}</b>", parse_mode="HTML")
    else:
        logging.info(f"Админ написал обычное сообщение (не Reply): {msg.text}")
        await msg.reply_text(
            "ℹ️ Чтобы ответить пользователю — нажми и удержи нужное сообщение от клиента, "
            "выбери «Ответить» (Reply), и только потом пиши текст.\n\n"
            f"Записей в памяти: {len(pending_replies)}"
        )

# ───── ОБРАБОТЧИК ОШИБОК ─────
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.error("Ошибка при обработке обновления:", exc_info=context.error)

# ───── ЗАПУСК ─────
async def main_async():
    request = HTTPXRequest(
        connect_timeout=30,
        read_timeout=30,
        write_timeout=30,
        pool_timeout=30,
    )
    app = Application.builder().token(TOKEN).request(request).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))

    # Все сообщения от админа (ответы + обычные)
    app.add_handler(MessageHandler(
        filters.Chat(ADMIN_ID) & filters.TEXT & ~filters.COMMAND,
        admin_any_message
    ))

    # Сообщения от пользователей (не от админа)
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & ~filters.Chat(ADMIN_ID),
        forward_to_admin
    ))

    app.add_error_handler(error_handler)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop_event.set)

    async with app:
        await app.start()
        await app.updater.start_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
        )
        await stop_event.wait()
        await app.updater.stop()
        await app.stop()

def main():
    while True:
        try:
            asyncio.run(main_async())
        except (KeyboardInterrupt, SystemExit):
            logging.info("Бот остановлен.")
            break
        except Exception as e:
            logging.error(f"Бот упал с ошибкой: {e}. Перезапускаю через 5 секунд...")
            import time
            time.sleep(5)

if __name__ == "__main__":
    main()
