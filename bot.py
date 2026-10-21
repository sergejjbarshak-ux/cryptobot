import os
import requests
from flask import Flask
from threading import Thread
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# Flask-сервер для удержания бота в сети 24/7 на Render
app_web = Flask('')

@app_web.route('/')
def home():
    return "Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

Thread(target=run_web, daemon=True).start()

BOT_TOKEN = "8850750621:AAHaNHjEZIhq3e4_Kc0u9dMGcCaGh_jpj5E"
CHECK_INTERVAL = 10

user_alerts = {}
alert_counter = 1
previous_prices = {}

def get_crypto_price(symbol: str):
    symbol = symbol.upper().strip()
    
    # Автоматически убираем суффикс USDT для поиска
    clean_symbol = symbol.replace("USDT", "").lower()
    
    url = f"https://api.coingecko.com/api/v3/search?query={clean_symbol}"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            coins = data.get("coins", [])
            if coins:
                # Берем самую первую подходящую монету из поиска
                coin_id = coins[0]["id"]
                
                # Запрашиваем актуальную цену по найденному ID
                price_url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd"
                p_resp = requests.get(price_url, headers=headers, timeout=5)
                if p_resp.status_code == 200:
                    p_data = p_resp.json()
                    if coin_id in p_data and "usd" in p_data[coin_id]:
                        return float(p_data[coin_id]["usd"])
    except Exception as e:
        print(f"Ошибка поиска цены для {symbol}: {e}")
        
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["🔔 Добавить алерт", "📋 Мои алерты"],
        ["🔍 Курс монет", "🗑 Удалить алерт"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    text = (
        "👋 Добро пожаловать в Crypto Notify BOT!\n\n"
        "Функции:\n"
        "• Многоразовые алерты\n"
        "• Быстрый курс монет в 1 клик\n"
        "• Детектор пампов и дампов\n\n"
        "Выберите нужный раздел в меню:"
    )
    await update.message.reply_text(text, reply_markup=reply_markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global alert_counter
    text = update.message.text
    chat_id = update.effective_chat.id

    if text == "🔔 Добавить алерт":
        await update.message.reply_text(
            "📥 Как добавить алерт:\n"
            "Отправьте сообщение в формате:\n"
            "ТИКЕР ЦЕНА\n\n"
            "Пример: BTCUSDT 85000 или APTUSDT 8.6 (работает любая монета!)"
        )
        
    elif text == "📋 Мои алерты":
        alerts = user_alerts.get(chat_id, [])
        if not alerts:
            await update.message.reply_text("📭 У вас пока нет активных алертов.")
        else:
            msg = "📋 Ваши многоразовые алерты:\n\n"
            for a in alerts:
                msg += f"ID: {a['id']} | Пара: {a['symbol']} | Цель: {a['target']}\n"
            msg += "\nДля удаления используйте: /del ID (например: /del 1)"
            await update.message.reply_text(msg)
            
    elif text == "🔍 Курс монет":
        symbols_to_check = ["BTCUSDT", "ETHUSDT", "APTUSDT", "SOLUSDT"]
        msg = "🔍 Актуальные курсы:\n\n"
        for sym in symbols_to_check:
            p = get_crypto_price(sym)
            if p is not None:
                msg += f"• {sym}: ${p}\n"
            else:
                msg += f"• {sym}: Ошибка загрузки\n"
        await update.message.reply_text(msg)

    elif text == "🗑 Удалить алерт":
        alerts = user_alerts.get(chat_id, [])
        if not alerts:
            await update.message.reply_text("📭 У вас нет алертов для удаления.")
        else:
            msg = "🗑 Список алертов для удаления:\n(Введите /del ID, например /del 1)\n\n"
            for a in alerts:
                msg += f"ID: {a['id']} — Пара: {a['symbol']} (Цель: {a['target']})\n"
            await update.message.reply_text(msg)
            
    else:
        parts = text.strip().split()
        if len(parts) >= 2:
            symbol = parts[0].upper()
            try:
                target_price = float(parts[1].replace(",", "."))
            except ValueError:
                await update.message.reply_text("❌ Неверный формат цены. Пример: BTCUSDT 85000")
                return

            current_price = get_crypto_price(symbol)
            if current_price is None:
                await update.message.reply_text(f"❌ Не удалось найти монету {symbol}.")
                return

            initial_side = "above" if current_price >= target_price else "below"
            
            if chat_id not in user_alerts:
                user_alerts[chat_id] = []

            new_alert = {
                "id": alert_counter,
                "symbol": symbol,
                "target": target_price,
                "last_side": initial_side
            }
            user_alerts[chat_id].append(new_alert)
            alert_id = alert_counter
            alert_counter += 1

            await update.message.reply_text(
                f"✅ Алерт {symbol} по цене {target_price} добавлен (ID: {alert_id})\n"
                f"Текущая цена: {current_price}"
            )
        else:
            await update.message.reply_text("Используйте кнопки меню или отправьте пару и цену (например: BTCUSDT 85000)")

async def delete_alert_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args
    if not args:
        await update.message.reply_text("❌ Укажите ID алерта. Пример: /del 1")
        return
    
    try:
        alert_id_to_del = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ Неверный формат ID.")
        return

    alerts = user_alerts.get(chat_id, [])
    initial_len = len(alerts)
    user_alerts[chat_id] = [a for a in alerts if a["id"] != alert_id_to_del]

    if len(user_alerts[chat_id]) < initial_len:
        await update.message.reply_text(f"🗑 Алерт с ID {alert_id_to_del} удален!")
    else:
        await update.message.reply_text(f"❌ Алерт с ID {alert_id_to_del} не найден.")

async def price_checker_job(context: ContextTypes.DEFAULT_TYPE):
    global previous_prices

    all_symbols = {"BTCUSDT", "ETHUSDT", "APTUSDT"}
    for chat_id, alerts in user_alerts.items():
        for a in alerts:
            all_symbols.add(a["symbol"])

    current_prices = {sym: get_crypto_price(sym) for sym in all_symbols}

    for sym, curr_p in current_prices.items():
        if curr_p is not None and sym in previous_prices:
            prev_p = previous_prices[sym]
            change_pct = ((curr_p - prev_p) / prev_p) * 100
            if abs(change_pct) >= 1.0:
                direction = "📈 РОСТ" if change_pct > 0 else "📉 ПАДЕНИЕ"
                vol_msg = f"⚡️ ВОЛАТИЛЬНОСТЬ: {sym} | {direction}: {change_pct:.2f}% | Цена: {curr_p}"
                for chat_id in user_alerts.keys():
                    await context.bot.send_message(chat_id=chat_id, text=vol_msg)
        if curr_p is not None:
            previous_prices[sym] = curr_p

    for chat_id, alerts in user_alerts.items():
        for alert in alerts:
            sym = alert["symbol"]
            curr_price = current_prices.get(sym)
            if curr_price is not None:
                current_side = "above" if curr_price >= alert["target"] else "below"
                
                if current_side != alert["last_side"]:
                    alert["last_side"] = current_side
                    msg = f"🚨 УРОВЕНЬ ДОСТИГНУТ!\nПара: {sym}\nЦена: {curr_price}\nЦель: {alert['target']}"
                    await context.bot.send_message(chat_id=chat_id, text=msg)

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("del", delete_alert_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(price_checker_job, interval=CHECK_INTERVAL, first=5)

    print("🚀 Суперагент запущен и мониторит рынок!")
    app.run_polling()
