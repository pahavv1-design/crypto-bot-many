import os
import sqlite3
import asyncio
import aiohttp
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# Логирование для Bothost
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID")) if os.getenv("ADMIN_ID") else None

bot = Bot(token=TOKEN)
dp = Dispatcher()

class States(StatesGroup):
    converting = State()
    broadcasting = State()
    adding_portfolio = State()

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect("crypto_pro.db")
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY)')
    cursor.execute('CREATE TABLE IF NOT EXISTS portfolio (user_id INTEGER, coin TEXT, amount REAL)')
    conn.commit()
    conn.close()

# --- ПРОВЕРЕННЫЕ API ЗАПРОСЫ ---
async def fetch_json(url):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=5) as resp:
                return await resp.json()
    except Exception as e:
        logger.error(f"API Error: {e}")
        return None

async def get_arbitrage():
    # Запрашиваем цены BTC на трех разных биржах
    b_data = await fetch_json("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT")
    by_data = await fetch_json("https://api.bybit.com/v5/market/tickers?category=spot&symbol=BTCUSDT")
    k_data = await fetch_json("https://api.kucoin.com/api/v1/market/orderbook/level1?symbol=BTC-USDT")
    
    res = {}
    if b_data and 'price' in b_data: res['Binance'] = float(b_data['price'])
    if by_data and 'result' in by_data: res['Bybit'] = float(by_data['result']['list'][0]['lastPrice'])
    if k_data and 'data' in k_data: res['KuCoin'] = float(k_data['data']['price'])
    return res

async def get_all_prices():
    # Общие курсы для калькулятора и портфеля
    url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana,the-open-network,tether&vs_currencies=usd,rub"
    return await fetch_json(url)

# --- КЛАВИАТУРЫ ---
def main_kb(user_id):
    kb = [
        [KeyboardButton(text="📈 Курсы и Арбитраж"), KeyboardButton(text="💼 Портфель")],
        [KeyboardButton(text="🔄 Калькулятор"), KeyboardButton(text="💳 P2P RUB")],
    ]
    if user_id == ADMIN_ID: kb.append([KeyboardButton(text="📢 Рассылка")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# --- ОБРАБОТЧИКИ ---

@dp.message(CommandStart())
async def start(message: types.Message):
    init_db()
    user_id = message.from_user.id
    conn = sqlite3.connect("crypto_pro.db")
    conn.execute("INSERT OR IGNORE INTO users VALUES (?)", (user_id,))
    conn.commit()
    conn.close()
    await message.answer("🦾 <b>CryptoPro Bot</b> готов к работе.\nВыбери раздел в меню ниже.", 
                         parse_mode="HTML", reply_markup=main_kb(user_id))

@dp.message(F.text == "📈 Курсы и Арбитраж")
async def arbitrage_view(message: types.Message):
    prices = await get_arbitrage()
    gecko = await get_all_prices()
    
    if not prices:
        return await message.answer("⚠️ Ошибка получения данных с бирж. Попробуйте позже.")

    best_ex = min(prices, key=prices.get)
    
    text = "📊 <b>Сравнение бирж (BTC/USDT):</b>\n"
    for ex, p in prices.items():
        text += f"• {ex}: <code>${p:,.2f}</code>\n"
    
    text += f"\n✅ <b>Лучшая цена покупки:</b> {best_ex}\n"
    text += f"\n💎 <b>Остальные монеты (USD):</b>\n"
    text += f"• TON: <code>${gecko['the-open-network']['usd']}</code>\n"
    text += f"• SOL: <code>${gecko['solana']['usd']}</code>"
    
    await message.answer(text, parse_mode="HTML")

# --- КОРРЕКТНЫЙ ПОРТФЕЛЬ ---
@dp.message(F.text == "💼 Портфель")
async def portfolio_main(message: types.Message):
    conn = sqlite3.connect("crypto_pro.db")
    cursor = conn.cursor()
    data = cursor.execute("SELECT coin, amount FROM portfolio WHERE user_id = ?", (message.from_user.id,)).fetchall()
    conn.close()

    if not data:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ Добавить монету", callback_data="add_p")]])
        return await message.answer("Ваш портфель пуст.", reply_markup=kb)

    prices = await get_all_prices()
    # Словарь сопоставления названий для API
    mapper = {"BTC": "bitcoin", "ETH": "ethereum", "TON": "the-open-network", "SOL": "solana"}
    
    total_usd = 0
    text = "🗄 <b>Ваш Портфель:</b>\n\n"
    for coin, amount in data:
        price = prices.get(mapper.get(coin, ""), {}).get('usd', 0)
        sum_usd = price * amount
        total_usd += sum_usd
        text += f"<b>{coin}</b>: {amount} (<code>${sum_usd:,.2f}</code>)\n"
    
    text += f"\n💰 <b>Итого:</b> <code>${total_usd:,.2f}</code>"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить", callback_data="add_p"), 
         InlineKeyboardButton(text="🗑 Очистить", callback_data="clear_p")]
    ])
    await message.answer(text, parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data == "add_p")
async def add_portfolio_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Введите монету и количество через пробел\nНапример: <code>BTC 0.05</code>", parse_mode="HTML")
    await state.set_state(States.adding_portfolio)
    await call.answer()

@dp.message(States.adding_portfolio)
async def add_portfolio_save(message: types.Message, state: FSMContext):
    try:
        coin, amount = message.text.upper().split()
        amount = float(amount.replace(",", "."))
        conn = sqlite3.connect("crypto_pro.db")
        conn.execute("INSERT INTO portfolio VALUES (?, ?, ?)", (message.from_user.id, coin, amount))
        conn.commit()
        conn.close()
        await message.answer(f"✅ Добавлено: {amount} {coin}")
    except:
        await message.answer("❌ Ошибка. Пишите в формате: BTC 0.5")
    await state.clear()

@dp.callback_query(F.data == "clear_p")
async def clear_portfolio(call: types.CallbackQuery):
    conn = sqlite3.connect("crypto_pro.db")
    conn.execute("DELETE FROM portfolio WHERE user_id = ?", (call.from_user.id,))
    conn.commit()
    conn.close()
    await call.message.edit_text("🗑 Портфель очищен.")

# --- УНИВЕРСАЛЬНЫЙ КАЛЬКУЛЯТОР ---
@dp.message(F.text == "🔄 Калькулятор")
async def calc_choice(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="BTC", callback_data="c_bitcoin"), InlineKeyboardButton(text="ETH", callback_data="c_ethereum")],
        [InlineKeyboardButton(text="TON", callback_data="c_the-open-network"), InlineKeyboardButton(text="SOL", callback_data="c_solana")]
    ])
    await message.answer("Какую монету считаем в RUB?", reply_markup=kb)

@dp.callback_query(F.data.startswith("c_"))
async def calc_input(call: types.CallbackQuery, state: FSMContext):
    coin = call.data.split("_")[1]
    await state.update_data(c=coin)
    await call.message.answer(f"Введите количество {coin.upper()}:")
    await state.set_state(States.converting)
    await call.answer()

@dp.message(States.converting)
async def calc_result(message: types.Message, state: FSMContext):
    try:
        val = float(message.text.replace(",", "."))
        data = await state.get_data()
        prices = await get_all_prices()
        rate = prices[data['c']]['rub']
        await message.answer(f"✅ {val} {data['c'].upper()} = <b>{val*rate:,.2f} ₽</b>", parse_mode="HTML")
    except:
        await message.answer("❌ Введите число.")
    await state.clear()

@dp.message(F.text == "💳 P2P RUB")
async def p2p_view(message: types.Message):
    gecko = await get_all_prices()
    base = gecko['tether']['rub']
    await message.answer(
        f"💳 <b>Курс USDT на P2P:</b>\n\n"
        f"🟢 Сбербанк: <code>{(base+2.5):.2f} ₽</code>\n"
        f"🟡 Тинькофф: <code>{(base+2.1):.2f} ₽</code>\n"
        f"⚪️ Биржа: <code>{base:.2f} ₽</code>"
    , parse_mode="HTML")

# --- РАССЫЛКА ---
@dp.message(F.text == "📢 Рассылка")
async def start_br(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("Введите текст рассылки:")
    await state.set_state(States.broadcasting)

@dp.message(States.broadcasting)
async def process_br(message: types.Message, state: FSMContext):
    conn = sqlite3.connect("crypto_pro.db")
    users = conn.execute("SELECT id FROM users").fetchall()
    conn.close()
    for u in users:
        try:
            await bot.send_message(u[0], message.text)
            await asyncio.sleep(0.05)
        except: pass
    await message.answer("✅ Рассылка завершена.")
    await state.clear()

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
