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

REPLIES_FILE  = "pending_replies.json"
FOLLOWUP_FILE = "followup_state.json"
MAX_REPLIES   = 500

def spots_left() -> str:
    # Лимит мест теперь 12
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


pending_replies: dict = load_replies()
followup_sent, user_engaged = load_followup_state()

WAITING_NAME, WAITING_PHONE = range(2)


# ───── МЕНЮ ─────

def main_menu():
    keyboard = [
        [InlineKeyboardButton("🎾 Программа и цена",    callback_data="programa")],
        [InlineKeyboardButton("🏡 Вилла и сервис",      callback_data="villa")],
        [InlineKeyboardButton("🌋 Вне корта",            callback_data="aktivnosti")],
        [InlineKeyboardButton("✈️ Визы и билеты",        callback_data="viza")],
        [InlineKeyboardButton("❓ Частые вопросы",       callback_data="faq")],
        [InlineKeyboardButton("📋 Забронировать место",  callback_data="booking")],
        [InlineKeyboardButton("💬 Задать вопрос",        callback_data="question")],
    ]
    return InlineKeyboardMarkup(keyboard)

def cancel_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("Отмена", callback_data="cancel_booking")]])

def back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("← Назад", callback_data="back")]])

def welcome_text(name: str) -> str:
    return (
        f"Привет, {name}.\n\n"
        "Теннисный и падел-кемп на Тенерифе. 20–26 октября 2026.\n\n"
        "Мы собираем 12 человек на частной вилле. С нас — личный повар, вечерние тренировки в Tenerife Tennis Academy и продуманный отдых. Яхта, вулкан Тейде, серфинг.\n\n"
        "Логистику, визы и билеты делаем «под ключ» вместе с партнерами VIZAGO.\n\n"
        f"Группа: 12 мест (осталось {spots_left()}).\n\n"
        "Кемп — 1 350 €\n"
        "Вилла — 600 €"
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

    await update.message.reply_text(welcome_text(user.first_name), parse_mode="HTML")
    await update.message.reply_text(
        "Выберите интересующий раздел:",
        reply_markup=main_menu()
    )

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

    if user.id not in followup_sent:
        asyncio.create_task(send_followup(context.bot, user.id, full_name))


# ───── КОМАНДА /menu ─────

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(welcome_text(user.first_name), parse_mode="HTML")
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
                "<b>Программа и цены</b>\n\n"
                "20–26 октября 2026 · Тенерифе · 12 человек\n\n"
                "━━━━━━━━━━━━━━━\n"
                "<b>Кемп — 1 350 €</b>\n\n"
                "🎾 <b>Спорт</b>\n"
                "6 вечерних тренировок в Tenerife Tennis Academy. Теннис или падел на выбор. Группы делим строго по уровню игры.\n\n"
                "🌋 <b>Приключения</b>\n"
                "Частная яхта, вулкан Тейде, Лоро-парк, Санта-Крус и серфинг.\n\n"
                "🚌 <b>Трансфер</b>\n"
                "Минивэн из аэропорта и для поездок по острову.\n\n"
                "━━━━━━━━━━━━━━━\n"
                "<b>Проживание — 600 €</b>\n\n"
                "🏡 6 ночей на вилле. Включены завтраки, обеды и ужины от личного шеф-повара.\n\n"
                "━━━━━━━━━━━━━━━\n"
                "<b>Перелёт и виза</b>\n"
                "Документы и билеты собираем «под ключ» (оплачивается отдельно). Партнеры — VIZAGO и Tenerife Tennis Academy."
            ),
            parse_mode="HTML",
            reply_markup=back_keyboard()
        )

    elif query.data == "villa":
        await query.edit_message_text(
            text=(
                "<b>Вилла и сервис</b>\n\n"
                "Мы сняли виллу на всю группу. Никаких отелей и посторонних людей.\n\n"
                "🏡 <b>6 ночей.</b> Бассейн, просторная терраса с видом на океан, тишина. Быта нет — уборку и рутину мы забрали на себя.\n\n"
                "👨‍🍳 <b>Шеф-повар</b>\n"
                "Завтраки, обеды и ужины готовятся на вилле. Фермерские продукты, свежая рыба. Заранее учитываем аллергии и ваши предпочтения.\n\n"
                "🛏 <b>Размещение</b>\n"
                "Подбираем так, чтобы никто не нарушал личные границы:\n"
                "· Отдельная комната\n"
                "· Комната на двоих (раздельные кровати)\n"
                "· Комната на двоих (одна большая кровать)\n\n"
                "До академии и кортов — 10–15 минут."
            ),
            parse_mode="HTML",
            reply_markup=back_keyboard()
        )

    elif query.data == "aktivnosti":
        await query.edit_message_text(
            text=(
                "<b>Вне корта</b>\n\n"
                "Сидеть на вилле всю неделю скучно, поэтому до тренировок мы исследуем остров. Всё это уже входит в 1 350 €, но участие — по вашему желанию.\n\n"
                "⛵ <b>Яхта</b>\n"
                "Частный чартер. Выходим в Атлантику, глушим мотор, купаемся.\n\n"
                "🌋 <b>Вулкан Тейде (3 718 м)</b>\n"
                "Подъем выше облаков. Никакой суеты, только марсианские пейзажи.\n\n"
                "🦜 <b>Лоро-парк (Loro Parque)</b>\n"
                "Один из лучших природных парков Европы.\n\n"
                "🏛 <b>Санта-Крус-де-Тенерифе</b>\n"
                "Едем в столицу за канарской архитектурой и местной кухней.\n\n"
                "🏄 <b>Серфинг</b>\n"
                "Берем доски и инструктора. Подходит для тех, кто ни разу не стоял на воде."
            ),
            parse_mode="HTML",
            reply_markup=back_keyboard()
        )

    elif query.data == "viza":
        await query.edit_message_text(
            text=(
                "<b>Визы и билеты</b>\n\n"
                "Мы забрали на себя всю бюрократию. Логистику закрывают наши партнёры VIZAGO и Tenerife Tennis Academy.\n\n"
                "🛂 <b>Шенген</b>\n"
                "Делаем «под ключ» через официальное спортивное приглашение от академии. Это дает высокий процент одобрения. Партнеры собирают документы, оформляют страховку и записывают в консульство.\n\n"
                "✈️ <b>Перелёт</b>\n"
                "Подбираем адекватные стыковки под ваши даты. Билеты оплачиваются отдельно.\n\n"
                "Вам нужно только передать паспорт. Рекомендуем бронировать место за 6–8 недель до вылета."
            ),
            parse_mode="HTML",
            reply_markup=back_keyboard()
        )

    elif query.data == "faq":
        await query.edit_message_text(
            text=(
                "<b>Частые вопросы</b>\n\n"
                "❓ <b>Я играю хуже/лучше остальных. Мне будет скучно?</b>\n"
                "Нет. Мы делим игроков по уровню. У новичков — база и отработка ударов. У продвинутых — интенсив и игра на счет.\n\n"
                "❓ <b>Ехать одному — это нормально?</b>\n"
                "Да. Больше половины группы прилетает поодиночке. Вечером первого дня все уже общаются на террасе. Формат на 12 человек располагает к правильному нетворкингу.\n\n"
                "❓ <b>Что входит в деньги?</b>\n"
                "Кемп (1 350 €): все тренировки, трансферы на острове, яхта, Тейде, столица, Лоро-парк, серфинг.\n"
                "Вилла (600 €): 6 ночей и питание от шеф-повара.\n"
                "Итого на острове: 1 950 €. Ваши билеты и виза оплачиваются отдельно.\n\n"
                "❓ <b>А если откажут в визе?</b>\n"
                "VIZAGO подает вас по спортивному приглашению академии, процент отказов минимален. Если это всё же случится — решаем ситуацию индивидуально.\n\n"
                "Остались вопросы? Пишите: @oceaninthesky"
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
        f"Забронировать место. Осталось {spots_left()} мест из 12.\n\n"
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
            CallbackQueryHandler(booking_cancel, pattern="^back$"),
            CommandHandler("start", start),
            CommandHandler("menu", menu_command),
        ],
        per_message=False,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(booking_conv)
    app.add_handler(CallbackQueryHandler(button))

    media_filter = (
        filters.PHOTO | filters.VOICE | filters.VIDEO |
        filters.Document.ALL | filters.Sticker.ALL | filters.VIDEO_NOTE
    ) & ~filters.Chat(ADMIN_ID)
    app.add_handler(MessageHandler(media_filter, forward_media_to_admin))

    app.add_handler(MessageHandler(
        filters.Chat(ADMIN_ID) & filters.TEXT & ~filters.COMMAND,
        admin_any_message
    ))

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