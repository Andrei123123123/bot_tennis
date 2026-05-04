from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

TOKEN = "СЮДА_ВСТАВЬ_ТОКЕН_ОТ_BOTFATHER"
ADMIN_ID = 123456789  # сюда вставь свой ID из @userinfobot

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

# ───── ВХОДЯЩИЕ СООБЩЕНИЯ → ТЕБЕ ─────
async def forward_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            f"📩 <b>Новый вопрос от клиента</b>\n\n"
            f"👤 {user.first_name} {user.last_name or ''}\n"
            f"📎 @{user.username or '—'}\n"
            f"🆔 <code>{user.id}</code>\n\n"
            f"💬 {text}"
        ),
        parse_mode="HTML"
    )

    await update.message.reply_text(
        f"Получил! Отвечу совсем скоро.\n\n"
        "Или напрямую: @oceaninthesky",
        reply_markup=main_menu()
    )

# ───── ЗАПУСК ─────
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, forward_to_admin))
    app.run_polling()

if __name__ == "__main__":
    main()