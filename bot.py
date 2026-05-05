import os
import asyncio
import signal
import logging
import json
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, filters, ContextTypes
)
from telegram.request import HTTPXRequest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN не найден в переменных окружения.")

ADMIN_ID = int(os.environ.get("ADMIN_CHAT_ID", "5495812267"))

REPLIES_FILE = "pending_replies.json"

def spots_left() -> str:
    return os.environ.get("SPOTS_LEFT", "14")

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

# Follow-up: отслеживаем пользователей
followup_sent: set[int] = set()      # кому уже отправили follow-up
user_engaged: set[int] = set()       # кто написал или нажал «Забронировать»

# ───── ФОТО АКТИВНОСТЕЙ ─────
# Вставь сюда прямые ссылки на фото (https://...) когда будут готовы
ACTIVITY_PHOTOS: list[str] = [
    # "https://ссылка-на-фото-яхты.jpg",
    # "https://ссылка-на-фото-тейде.jpg",
    # "https://ссылка-на-фото-замка.jpg",
]

# ───── СОСТОЯНИЯ ФОРМЫ БРОНИРОВАНИЯ ─────
WAITING_NAME, WAITING_PHONE = range(2)

# ───── МЕНЮ ─────
def main_menu():
    keyboard = [
        [InlineKeyboardButton("Программа и цены", callback_data="programa")],
        [InlineKeyboardButton("О кемпе", callback_data="about")],
        [InlineKeyboardButton("Активности", callback_data="aktivnosti")],
        [InlineKeyboardButton("Виза", callback_data="viza")],
        [InlineKeyboardButton("Забронировать место", callback_data="booking")],
        [InlineKeyboardButton("Задать вопрос", callback_data="question")],
    ]
    return InlineKeyboardMarkup(keyboard)

def cancel_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("Отмена", callback_data="cancel_booking")]])

def back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("← Назад", callback_data="back")]])

# ───── FOLLOW-UP ЗАДАЧА ─────
async def send_followup(bot, user_id: int, user_name: str):
    await asyncio.sleep(24 * 60 * 60)
    if user_id in user_engaged or user_id in followup_sent:
        return
    try:
        await bot.send_message(
            chat_id=user_id,
            text="Если остались вопросы — пиши, отвечу быстро. @oceaninthesky",
        )
        followup_sent.add(user_id)
        logging.info(f"Follow-up отправлен: {user_name} ({user_id})")
    except Exception as e:
        logging.warning(f"Не удалось отправить follow-up пользователю {user_id}: {e}")

# ───── СТАРТ ─────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    name = user.first_name
    full_name = f"{user.first_name} {user.last_name or ''}".strip()
    username_str = f"@{user.username}" if user.username else "—"

    await update.message.reply_text(
        f"Привет, {name}.\n\n"
        "Теннис и падел кемп на Тенерифе. 14–20 сентября 2026.\n\n"
        "7 дней на Канарских островах. Вилла с личным поваром. "
        "6 тренировок в Tenerife Tennis Academy — теннис или падел, выбираешь каждый день. "
        "Яхта, вулкан Тейде, сёрфинг, банкет в замке. "
        "Шенген по приглашению от академии.\n\n"
        f"Группа — 14 человек. Осталось {spots_left()} мест.\n\n"
        "В любой момент напиши /menu чтобы вернуться в меню.",
        reply_markup=main_menu()
    )

    # Уведомляем организатора о новом пользователе
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"🆕 Новый пользователь: <b>{full_name}</b> ({username_str})\n"
                f"🆔 <code>{user.id}</code>"
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        logging.warning(f"Не удалось уведомить админа о новом пользователе: {e}")

    # Запускаем follow-up через 24 часа
    if user.id not in followup_sent:
        asyncio.create_task(send_followup(context.bot, user.id, full_name))

# ───── МЕНЮ КОМАНДА ─────
async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Выбери что тебя интересует:",
        reply_markup=main_menu()
    )

# ───── КНОПКИ ─────
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "programa":
        await query.edit_message_text(
            text=(
                "<b>Программа и цены</b>\n\n"
                "14–20 сентября 2026 · Тенерифе · 14 человек\n\n"
                "━━━━━━━━━━━━━━━\n"
                "<b>Кемп — 110 000 ₽</b>\n"
                "· 6 тренировок в Tenerife Tennis Academy\n"
                "· Русскоязычный тренер\n"
                "· Теннис или падел — выбираешь каждый день\n"
                "· Все активности: яхта, Тейде, Маска, сёрфинг, банкет в замке\n"
                "· Трансфер аэропорт ↔ вилла\n"
                "· Питание: завтрак + обед + ужин (личный повар, всё включено)\n\n"
                "<b>Вилла — 50 000 ₽</b>\n"
                "· 7 ночей, вилла на всю группу, бассейн, Wi-Fi\n\n"
                "<b>Авиабилеты — ~90 000 ₽</b>\n"
                "· Помогаем подобрать оптимальный рейс\n\n"
                "<b>Виза — ~20 000 ₽</b>\n"
                "· Шенгенская виза через приглашение от академии\n"
                "· Партнёр ВизаGO — 500+ виз, 97% одобрение\n\n"
                "━━━━━━━━━━━━━━━\n"
                "<b>Итого с перелётом и визой: ~270 000 ₽</b>\n\n"
                "Депозит для брони: 33 000 ₽\n"
                "Остаток — двумя платежами до сентября."
            ),
            parse_mode="HTML",
            reply_markup=back_keyboard()
        )

    elif query.data == "about":
        await query.edit_message_text(
            text=(
                "Есть острова, которые существуют сами по себе. Тенерифе — один из них.\n\n"
                "Вулкан 3718 метров, видный с любой точки острова. "
                "Атлантика — с одной стороны тёплая и спокойная, с другой дикая и с волнами. "
                "Чёрные пляжи, ущелья, испанская кухня без туристических наценок.\n\n"
                "Мы арендовали виллу на всю группу. Наняли повара. "
                "Договорились с Tenerife Tennis Academy — академией, "
                "где тренируются спортсмены из Англии, Германии, Скандинавии.\n\n"
                "Утром — остров. Вечером — корт. Ночью — ужин на террасе, "
                "рыба с местного рынка и вино, которое здесь дешевле воды.\n\n"
                "Семь дней. Четырнадцать человек. "
                "Это не тур и не спортлагерь. "
                "Это неделя, после которой сложно вернуться к обычному сентябрю."
            ),
            parse_mode="HTML",
            reply_markup=back_keyboard()
        )

    elif query.data == "aktivnosti":
        aktivnosti_text = (
            "<b>Активности</b>\n\n"
            "Каждое утро — новое приключение:\n\n"
            "⛵ <b>Яхта</b>\n"
            "Выход в океан, купание, дельфины\n\n"
            "🌋 <b>Вулкан Тейде, 3718 м</b>\n"
            "Самая высокая точка Испании\n\n"
            "🏔 <b>Ущелье Маска</b>\n"
            "Хайкинг по одному из красивейших маршрутов Канар\n\n"
            "🏄 <b>Сёрфинг</b>\n"
            "С инструктором, для любого уровня\n\n"
            "🏰 <b>Банкет в замке Сан-Мигель</b>\n"
            "Рыцарское шоу, ужин, живая история\n\n"
            "Все активности включены в стоимость кемпа."
        )
        if ACTIVITY_PHOTOS:
            media = [InputMediaPhoto(media=url) for url in ACTIVITY_PHOTOS]
            media[0] = InputMediaPhoto(
                media=ACTIVITY_PHOTOS[0], caption=aktivnosti_text, parse_mode="HTML"
            )
            await query.message.reply_media_group(media=media)
            await query.edit_message_text(
                "Смотри фото активностей выше 👆",
                reply_markup=back_keyboard()
            )
        else:
            await query.edit_message_text(
                text=aktivnosti_text,
                parse_mode="HTML",
                reply_markup=back_keyboard()
            )

    elif query.data == "viza":
        await query.edit_message_text(
            text=(
                "<b>Виза</b>\n\n"
                "Тенерифе — Испания, нужен шенген.\n\n"
                "Оформляем через спортивное приглашение от Tenerife Tennis Academy — "
                "это официальный документ, который значительно повышает шансы на одобрение.\n\n"
                "<b>Всем занимается партнёр ВизаGO:</b>\n"
                "· Приглашение от академии\n"
                "· Сбор документов\n"
                "· Запись в консульство\n"
                "· 500+ виз, 97% одобрение\n\n"
                "Стоимость: ~20 000 ₽\n"
                "Срок рассмотрения: 2–4 недели\n\n"
                "Бронируй минимум за 6 недель до вылета."
            ),
            parse_mode="HTML",
            reply_markup=back_keyboard()
        )

    elif query.data == "question":
        user_engaged.add(query.from_user.id)
        await query.edit_message_text(
            text=(
                "<b>Задать вопрос</b>\n\n"
                "Напиши свой вопрос прямо здесь — "
                "организатор получит его и ответит лично.\n\n"
                "Или сразу в личку: @oceaninthesky"
            ),
            parse_mode="HTML",
            reply_markup=back_keyboard()
        )

    elif query.data == "back":
        await query.edit_message_text(
            "Выбери что тебя интересует:",
            reply_markup=main_menu()
        )

# ───── ФОРМА БРОНИРОВАНИЯ ─────
async def booking_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_engaged.add(query.from_user.id)
    await query.edit_message_text(
        "<b>Забронировать место</b>\n\n"
        f"Осталось {spots_left()} мест из 14.\n\n"
        "Оставь заявку — мы свяжемся в течение нескольких часов, "
        "ответим на все вопросы и зафиксируем место.\n\n"
        "Как тебя зовут? (имя и фамилия)",
        parse_mode="HTML",
        reply_markup=cancel_keyboard()
    )
    return WAITING_NAME

async def booking_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["booking_name"] = update.message.text
    user_engaged.add(update.effective_user.id)
    await update.message.reply_text(
        "Теперь укажи номер телефона или @username в Telegram:",
        reply_markup=cancel_keyboard()
    )
    return WAITING_PHONE

async def booking_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    name = context.user_data.get("booking_name", "—")
    phone = update.message.text
    username_str = f"@{user.username}" if user.username else "—"
    user_engaged.add(user.id)

    sent = await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            f"🎾 <b>Новая заявка на кемп!</b>\n\n"
            f"👤 <b>{name}</b>\n"
            f"📞 {phone}\n"
            f"📎 {username_str}\n"
            f"🆔 <code>{user.id}</code>\n\n"
            f"⬆️ <b>Ответь на это сообщение</b> — и ответ уйдёт клиенту."
        ),
        parse_mode="HTML"
    )
    pending_replies[sent.message_id] = (user.id, name)
    save_replies(pending_replies)

    share_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "Поделиться с другом",
            url="https://t.me/share/url?url=https://t.me/tennis_tenerife&text=Теннисный+и+падел+кемп+на+Тенерифе+%E2%80%94+14-20+сентября+2026"
        )],
        [InlineKeyboardButton("← В меню", callback_data="back")],
    ])

    await update.message.reply_text(
        "<b>Заявка принята.</b>\n\n"
        "Свяжемся в ближайшие несколько часов.\n\n"
        "Приведи друга — он получит скидку 5 000 ₽, ты — бонус.",
        parse_mode="HTML",
        reply_markup=share_keyboard
    )
    return ConversationHandler.END

async def booking_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Выбери что тебя интересует:",
        reply_markup=main_menu()
    )
    return ConversationHandler.END

# ───── ВХОДЯЩИЕ СООБЩЕНИЯ → АДМИНУ ─────
async def forward_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text
    full_name = f"{user.first_name} {user.last_name or ''}".strip()
    username_str = f"@{user.username}" if user.username else "—"
    user_engaged.add(user.id)

    sent = await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            f"┌ 📩 <b>Вопрос от: {full_name}</b> ({username_str})\n"
            f"└ 🆔 <code>{user.id}</code>\n\n"
            f"💬 {text}\n\n"
            f"⬆️ <b>Ответь на это сообщение</b> — и ответ уйдёт {full_name}."
        ),
        parse_mode="HTML"
    )
    pending_replies[sent.message_id] = (user.id, full_name)
    save_replies(pending_replies)

    await update.message.reply_text(
        "Получил. Отвечу в ближайшее время.\n\n"
        "Или напрямую: @oceaninthesky",
        reply_markup=main_menu()
    )

# ───── МЕДИАФАЙЛЫ ОТ ПОЛЬЗОВАТЕЛЕЙ ─────
async def forward_media_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    full_name = f"{user.first_name} {user.last_name or ''}".strip()
    username_str = f"@{user.username}" if user.username else "—"
    user_engaged.add(user.id)

    msg = update.message
    if msg.photo:
        media_type = "фото"
    elif msg.voice:
        media_type = "голосовое"
    elif msg.video:
        media_type = "видео"
    elif msg.document:
        media_type = "документ"
    elif msg.sticker:
        media_type = "стикер"
    elif msg.video_note:
        media_type = "видеосообщение"
    else:
        media_type = "файл"

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            f"┌ 📎 <b>{media_type.capitalize()} от: {full_name}</b> ({username_str})\n"
            f"└ 🆔 <code>{user.id}</code>"
        ),
        parse_mode="HTML"
    )
    await context.bot.forward_message(
        chat_id=ADMIN_ID,
        from_chat_id=msg.chat_id,
        message_id=msg.message_id
    )

    await update.message.reply_text(
        "Получил. Отвечу в ближайшее время.\n\n"
        "Или напрямую: @oceaninthesky",
        reply_markup=main_menu()
    )

# ───── СООБЩЕНИЯ ОТ АДМИНА ─────
async def admin_any_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.reply_to_message:
        replied_id = msg.reply_to_message.message_id
        entry = pending_replies.get(replied_id)
        logging.info(
            f"Админ ответил на msg_id={replied_id}. "
            f"Найдено: {entry}. Всего: {len(pending_replies)}"
        )
        if not entry:
            await msg.reply_text(
                f"⚠️ Не нашёл пользователя для этого сообщения.\n"
                f"Записей в памяти: {len(pending_replies)}\n"
                f"ID сообщения: {replied_id}\n\n"
                f"Попроси пользователя написать снова."
            )
            return

        user_chat_id, user_name = entry
        await context.bot.send_message(
            chat_id=user_chat_id,
            text=f"💬 <b>Ответ организатора:</b>\n\n{msg.text}",
            parse_mode="HTML",
            reply_markup=main_menu()
        )
        await msg.reply_text(
            f"✅ Ответ отправлен → <b>{user_name}</b>", parse_mode="HTML"
        )
    else:
        await msg.reply_text(
            "ℹ️ Чтобы ответить пользователю — нажми и удержи нужное сообщение, "
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

    # Форма бронирования
    booking_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(booking_start, pattern="^booking$")],
        states={
            WAITING_NAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & ~filters.Chat(ADMIN_ID),
                    booking_name
                ),
                CallbackQueryHandler(booking_cancel, pattern="^cancel_booking$"),
            ],
            WAITING_PHONE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & ~filters.Chat(ADMIN_ID),
                    booking_phone
                ),
                CallbackQueryHandler(booking_cancel, pattern="^cancel_booking$"),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(booking_cancel, pattern="^cancel_booking$"),
            CommandHandler("start", start),
            CommandHandler("menu", menu_command),
        ],
        per_message=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(booking_conv)
    app.add_handler(CallbackQueryHandler(button))

    # Медиафайлы от пользователей
    media_filter = (
        filters.PHOTO | filters.VOICE | filters.VIDEO |
        filters.Document.ALL | filters.Sticker.ALL | filters.VIDEO_NOTE
    ) & ~filters.Chat(ADMIN_ID)
    app.add_handler(MessageHandler(media_filter, forward_media_to_admin))

    # Сообщения от админа
    app.add_handler(MessageHandler(
        filters.Chat(ADMIN_ID) & filters.TEXT & ~filters.COMMAND,
        admin_any_message
    ))

    # Текстовые сообщения от пользователей
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
            time.sleep(5)

if __name__ == "__main__":
    main()
