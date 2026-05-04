# Telegram Camp Bot

A Telegram bot (in Russian) that promotes and handles inquiries/bookings for a tennis and padel camp in Tenerife (September 14–20, 2026).

## Architecture

- **Language**: Python 3.12
- **Framework**: python-telegram-bot 20.7 (long-polling, async)
- **Entry point**: `bot.py`
- **Dependencies**: `requirements.txt`

## Features

- `/start` command sends camp info with an inline keyboard menu
- Menu buttons: Program & Prices, Visa, Booking, Ask a Question
- User messages are forwarded to the admin's Telegram chat (ADMIN_ID)
- Users get a confirmation reply when they send a message

## Configuration

- `TELEGRAM_BOT_TOKEN` — stored as a Replit Secret (environment variable)
- `ADMIN_ID` — hardcoded in `bot.py` (Telegram user ID: 5495812267)

## Running

The bot runs as a console workflow: `python bot.py`
