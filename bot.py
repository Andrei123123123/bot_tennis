import os
import asyncio
import signal
import logging
import json
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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

REPLIES_FILE   = "pending_replies.json"
FOLLOWUP_FILE  = "followup_state.json"
MAX_REPLIES    = 500   # максимум записей в pending_replies

def spots_left() -> str:
    return os.environ.get("SPOTS_LEFT", "12")


# ───── ПЕРСИСТЕНТНОЕ ХРАНИЛИЩЕ ─────

def load_replies() -> dict:
    if os.path.exists(REPLIES_FILE):
        try:
            with open(REPLIES_FILE, "r") as f:
                data = json.load(f)
                return {int(k): tuple(v) for k, v in data.items()}
        except Exception:
            pass
    return {}

def save_replies(data: dict):
    # Оставляем только последние MAX_REPLIES записей
    if len(data) > MAX_REPLIES:
        keys = sorted(data.keys())
        for k in keys[:len(data) - MAX_REPLIES]:
            del data[k]
    with open(REPLIES_FILE, "w") as f:
        json.dump({str(k): list(v) for k, v in data.items()}, f)

def load_followup_state() -> tuple[set, set]:
    if os.path.exists(FOLLOWUP_FILE):
        try:
            with open(FOLLOWUP_FILE, "r") as f:
                data = json.load(f)
                return set(data.get("sent", [])), set(data.get("engaged", []))
        except Exception:
            pass
    return set(), set()

def save_followup_state():
    with open(FOLLOWUP_FILE, "w") as f:
        json.dump({
            "sent":    list(followup_sent),
            "engaged": list(user_engaged),
        }, f)


# {message_id пересланного сообщения → (chat_id пользователя, имя)}
pending_replies: dict = load_replies()

# Follow-up: персистентное отслеживание
followup_sent, user_engaged = load_followup_state()

# Состояния формы бронирования
WAITING_NAME, WAITING_PHONE = range(2)


# ───── МЕНЮ ─────

def main_menu():
    keyboard = [
        [InlineKeyboardButton("🎾 Программа и цена (1 350 €)", callback_data="programa")],
        [InlineKeyboardButton("🏡 Вилла и сервис",             callback_data="villa")],
        [InlineKeyboardButton("🌋 Активности вне корта",       callback_data="aktivnosti")],
        [InlineKeyboardButton("✈️ Виза и перелёт",             callback_data="viza")],
        [InlineKeyboardButton("❓ Частые вопросы",             callback_data="faq")],
        [InlineKeyboardButton("📋 Забронировать место",        callback_data="booking")],
        [InlineKeyboardButton("💬 Задать вопрос",              callback_data="question")],
    ]
    return InlineKeyboardMarkup(keyboard)

def cancel_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("Отмена", callback_data="cancel_booking")]])

def back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("← Назад", callback_data="back")]])

def welcome_text(name: str) -> str:
    return (
        f"Добрый день, {name}.\n\n"
        "Теннис и падел-кемп на Тенерифе. 20–26 октября 2026.\n\n"
        "7 дней на Канарских островах: вилла с личным поваром, "
        "6 тренировок в Tenerife Tennis Academy, "
        "яхта, вулкан Тейде, серфинг. "
        "Шенген по спортивному приглашению от академии.\n\n"
        f"Группа — 12 человек. Осталось {spots_left()} мест.\n"
        "Стоимость — 1 350 €. Перелёт и виза — отдельно."
    )


# ───── FOLLOW-UP ЧЕРЕЗ 24 ЧАСА ─────

async def send_followup(bot, user_id: int, user_name: str):
    await asyncio.sleep(24 * 60 * 60)
    if user_id in user_engaged or user_id in followup_sent:
        return
    try:
        await bot.send_message(
            chat_id=user_id,
            text="Если остались вопросы по кемпу — пишите прямо сюда, отвечу лично.",
        )
        followup_sent.add(user_id)
        save_followup_state()
        logging.info(f"Follow-up отправлен: {user_name} ({user_id})")
    except Exception as e:
        logging.warning(f"Не удалось отправить follow-up {user_id}: {e}")


# ───── СТАРТ ─────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    full_name = f"{user.first_name} {user.last_name or ''}".strip()
    username_str = f"@{user.username}" if user.username else "—"

    # Сообщение 1: приветствие — никогда не редактируется
    await update.message.reply_text(welcome_text(user.first_name))

    # Сообщение 2: меню — только оно редактируется при навигации
    await update.message.reply_text(
        "Выберите интересующий раздел:",
        reply_markup=main_menu()
    )

    # Уведомление организатору
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
        logging.warning(f"Не удалось уведомить админа: {e}")

    # Follow-up через 24 часа
    if user.id not in followup_sent:
        asyncio.create_task(send_followup(context.bot, user.id, full_name))


# ───── КОМАНДА /menu ─────

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    # Сообщение 1: приветствие
    await update.message.reply_text(welcome_text(user.first_name))
    # Сообщение 2: меню
    await update.message.reply_text(
        "Выберите интересующий раздел:",
        reply_markup=main_menu()
    )


# ───── КНОПКИ ─────

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "programa":
        await query.edit_message_text(
            text=(
                "<b>Программа и цена</b>\n\n"
                "20–26 октября 2026 · Тенерифе · 12 человек\n\n"
                "━━━━━━━━━━━━━━━\n"
                "<b>1 350 € — всё включено:</b>\n\n"
                "🎾 6 тренировок в Tenerife Tennis Academy\n"
                "Теннис или падел — выбираете каждый день. Русскоязычный тренер.\n\n"
                "🏡 Проживание на вилле — 7 ночей\n"
                "Вилла на всю группу. Бассейн, терраса, общие зоны.\n\n"
                "👨‍🍳 Питание\n"
                "Завтрак, обед и ужин — шеф-повар. Всё на вилле.\n\n"
                "🚌 Трансфер\n"
                "Аэропорт ↔ вилла включён.\n\n"
                "🌋 Все активности\n"
                "Яхта, вулкан Тейде, ущелье Маска, серфинг, банкет в замке.\n\n"
                "━━━━━━━━━━━━━━━\n"
                "Оплачивается отдельно:\n"
                "· Перелёт — от 600 €\n"
                "· Виза — около 200 €\n\n"
                "Депозит для фиксации места: 350 €\n"
                "Остаток — двумя платежами до октября."
            ),
            parse_mode="HTML",
            reply_markup=back_keyboard()
        )

    elif query.data == "villa":
        await query.edit_message_text(
            text=(
                "<b>Вилла и сервис</b>\n\n"
                "Вилла арендована целиком — только ваша группа, никаких посторонних.\n\n"
                "🏡 Бассейн, терраса, общие зоны для отдыха. "
                "7 ночей без бытовых забот: уборка, питание и всё необходимое организовано.\n\n"
                "👨‍🍳 Личный шеф-повар на весь кемп.\n"
                "Завтрак, обед, ужин — на вилле. "
                "Меню согласовывается заранее с учётом предпочтений группы.\n\n"
                "📶 Wi-Fi, всё необходимое для комфортного проживания.\n\n"
                "Вилла расположена в удобной точке острова — "
                "10–15 минут до академии и основных активностей."
            ),
            parse_mode="HTML",
            reply_markup=back_keyboard()
        )

    elif query.data == "aktivnosti":
        await query.edit_message_text(
            text=(
                "<b>Активности вне корта</b>\n\n"
                "Участие в каждой активности — по желанию.\n\n"
                "⛵ Яхта\n"
                "Выход в Атлантику, купание в открытом океане.\n\n"
                "🌋 Вулкан Тейде — 3 718 м\n"
                "Самая высокая точка Испании. Панорама острова с вершины.\n\n"
                "🏔 Ущелье Маска\n"
                "Один из наиболее живописных маршрутов Канарских островов.\n\n"
                "🏄 Серфинг\n"
                "С инструктором, подходит для любого уровня.\n\n"
                "🏰 Банкет в замке Сан-Мигель\n"
                "Исторический замок, ужин, живое шоу.\n\n"
                "Все активности включены в стоимость кемпа."
            ),
            parse_mode="HTML",
            reply_markup=back_keyboard()
        )

    elif query.data == "viza":
        await query.edit_message_text(
            text=(
                "<b>Виза и перелёт</b>\n\n"
                "✈️ <b>Перелёт</b>\n"
                "Тенерифе-Юг (TFS) — прямые рейсы из Москвы и Санкт-Петербурга. "
                "Стоимость от 600 €. Помогаем подобрать подходящий рейс.\n\n"
                "🛂 <b>Виза</b>\n"
                "Тенерифе — Испания, требуется шенгенская виза.\n\n"
                "Оформляется через партнёра <b>VIZAGO</b> под ключ, "
                "на основе спортивного приглашения от Tenerife Tennis Academy.\n\n"
                "Что входит в услугу VIZAGO:\n"
                "· Получение приглашения от академии\n"
                "· Подготовка документов\n"
                "· Запись в консульство\n\n"
                "Стоимость: около 200 €\n"
                "Срок оформления: 2–4 недели\n\n"
                "Рекомендуем бронировать место минимум за 6–8 недель до вылета."
            ),
            parse_mode="HTML",
            reply_markup=back_keyboard()
        )

    elif query.data == "faq":
        await query.edit_message_text(
            text=(
                "<b>Частые вопросы</b>\n\n"
                "❓ <b>Какой уровень игры необходим?</b>\n"
                "Любой. Кемп подходит и начинающим, и тем, кто играет годами. "
                "Тренер адаптирует нагрузку под каждого участника.\n\n"
                "❓ <b>Можно играть и теннис, и падел?</b>\n"
                "Да. Каждый день вы выбираете дисциплину самостоятельно.\n\n"
                "❓ <b>Можно приехать одному, без компании?</b>\n"
                "Да. Большинство участников едут именно так. "
                "Группа — 12 человек, формат располагает к знакомствам.\n\n"
                "❓ <b>Что входит в стоимость 1 350 €?</b>\n"
                "Проживание (7 ночей), питание (шеф-повар), "
                "6 тренировок, трансфер, все активности. "
                "Перелёт и виза — отдельно.\n\n"
                "❓ <b>Как устроена оплата?</b>\n"
                "Депозит 350 € — для фиксации места. "
                "Остаток — двумя платежами до октября.\n\n"
                "❓ <b>Что если в визе откажут?</b>\n"
                "VIZAGO работает на основе официального спортивного приглашения. "
                "В случае отказа обсуждаем индивидуально.\n\n"
                "❓ <b>Когда лучше бронировать?</b>\n"
                f"Как можно раньше. Осталось {spots_left()} мест из 12. "
                "На оформление визы нужно минимум 6–8 недель.\n\n"
                "❓ <b>Что взять с собой?</b>\n"
                "Ракетку (можно взять на месте), спортивную форму, солнцезащитный крем. "
                "Полный список пришлём после бронирования.\n\n"
                "Остались вопросы — напишите: @oceaninthesky"
            ),
            parse_mode="HTML",
            reply_markup=back_keyboard()
        )

    elif query.data == "question":
        user_engaged.add(query.from_user.id)
        save_followup_state()
        await query.edit_message_text(
            text=(
                "Напишите ваш вопрос прямо здесь — "
                "организатор получит его и ответит лично.\n\n"
                "Или напрямую: @oceaninthesky"
            ),
            reply_markup=back_keyboard()
        )

    elif query.data == "back":
        await query.edit_message_text(
            "Выберите интересующий раздел:",
            reply_markup=main_menu()
        )


# ───── ФОРМА БРОНИРОВАНИЯ ─────

async def booking_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_engaged.add(query.from_user.id)
    save_followup_state()
    await query.edit_message_text(
        f"Забронировать место.\n\n"
        f"Осталось {spots_left()} мест из 12.\n\n"
        "Как к вам обращаться? (Имя и фамилия)",
        reply_markup=cancel_keyboard()
    )
    return WAITING_NAME

async def booking_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["booking_name"] = update.message.text
    user_engaged.add(update.effective_user.id)
    save_followup_state()
    await update.message.reply_text(
        "Оставьте ваш номер телефона или @username в Telegram.",
        reply_markup=cancel_keyboard()
    )
    return WAITING_PHONE

async def booking_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    name = context.user_data.get("booking_name", "—")
    phone = update.message.text
    username_str = f"@{user.username}" if user.username else "—"
    user_engaged.add(user.id)
    save_followup_state()

    sent = await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            f"📋 <b>Новая заявка на кемп</b>\n\n"
            f"👤 {name}\n"
            f"📞 {phone}\n"
            f"📎 {username_str}\n"
            f"🆔 <code>{user.id}</code>\n\n"
            f"Ответьте на это сообщение — ответ уйдёт клиенту."
        ),
        parse_mode="HTML"
    )
    pending_replies[sent.message_id] = (user.id, name)
    save_replies(pending_replies)

    await update.message.reply_text(
        "Заявка принята.\n\n"
        "Организатор свяжется с вами в течение пары часов, "
        "чтобы обсудить ваш уровень игры и подобрать подходящую комнату на вилле.",
        reply_markup=back_keyboard()
    )
    return ConversationHandler.END

async def booking_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Выберите интересующий раздел:",
        reply_markup=main_menu()
    )
    return ConversationHandler.END


# ───── ВХОДЯЩИЕ СООБЩЕНИЯ → ОРГАНИЗАТОРУ ─────

async def forward_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text
    full_name = f"{user.first_name} {user.last_name or ''}".strip()
    username_str = f"@{user.username}" if user.username else "—"
    user_engaged.add(user.id)
    save_followup_state()

    sent = await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            f"💬 <b>Вопрос от: {full_name}</b> ({username_str})\n"
            f"🆔 <code>{user.id}</code>\n\n"
            f"{text}\n\n"
            f"Ответьте на это сообщение — ответ уйдёт клиенту."
        ),
        parse_mode="HTML"
    )
    pending_replies[sent.message_id] = (user.id, full_name)
    save_replies(pending_replies)

    await update.message.reply_text(
        "Сообщение получено. Ответим в ближайшее время.\n\n"
        "Или напрямую: @oceaninthesky",
        reply_markup=main_menu()
    )


# ───── МЕДИАФАЙЛЫ ОТ ПОЛЬЗОВАТЕЛЕЙ ─────

async def forward_media_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    full_name = f"{user.first_name} {user.last_name or ''}".strip()
    username_str = f"@{user.username}" if user.username else "—"
    user_engaged.add(user.id)
    save_followup_state()

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

    # Сохраняем уведомление в pending_replies — чтобы организатор мог ответить
    sent = await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            f"📎 <b>{media_type.capitalize()} от: {full_name}</b> ({username_str})\n"
            f"🆔 <code>{user.id}</code>\n\n"
            f"Ответьте на это сообщение — ответ уйдёт клиенту."
        ),
        parse_mode="HTML"
    )
    pending_replies[sent.message_id] = (user.id, full_name)
    save_replies(pending_replies)

    await context.bot.forward_message(
        chat_id=ADMIN_ID,
        from_chat_id=msg.chat_id,
        message_id=msg.message_id
    )

    await update.message.reply_text(
        "Сообщение получено. Ответим в ближайшее время.\n\n"
        "Или напрямую: @oceaninthesky",
        reply_markup=main_menu()
    )


# ───── ОТВЕТЫ ОРГАНИЗАТОРА → ПОЛЬЗОВАТЕЛЮ ─────

async def admin_any_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.reply_to_message:
        replied_id = msg.reply_to_message.message_id
        entry = pending_replies.get(replied_id)
        logging.info(f"Reply на msg_id={replied_id}. Найдено: {entry}. Записей: {len(pending_replies)}")
        if not entry:
            await msg.reply_text(
                f"Не нашёл пользователя для этого сообщения.\n"
                f"Записей в памяти: {len(pending_replies)}\n"
                f"ID сообщения: {replied_id}\n\n"
                f"Попросите пользователя написать снова."
            )
            return

        user_chat_id, user_name = entry
        await context.bot.send_message(
            chat_id=user_chat_id,
            text=f"<b>Ответ организатора:</b>\n\n{msg.text}",
            parse_mode="HTML",
            reply_markup=main_menu()
        )
        await msg.reply_text(
            f"Ответ отправлен → <b>{user_name}</b>", parse_mode="HTML"
        )
    else:
        await msg.reply_text(
            "Чтобы ответить пользователю — нажмите и удержите нужное сообщение, "
            "выберите «Ответить» (Reply), и только затем вводите текст.\n\n"
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
    # per_message=False — состояние привязано к пользователю, не к сообщению
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
        per_message=False,
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

    # Сообщения от организатора
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
            logging.error(f"Бот упал с ошибкой: {e}. Перезапуск через 5 секунд...")
            time.sleep(5)


if __name__ == "__main__":
    main()
