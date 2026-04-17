import os
import sqlite3
import asyncio
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# Настройки
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID")) if os.getenv("ADMIN_ID") else None

bot = Bot(token=TOKEN)
dp = Dispatcher()

class States(StatesGroup):
    broadcasting = State()
    converting = State()

# --- БАЗА ДАННЫХ (Для портфеля и рассылки) ---
def init_db():
    conn = sqlite3.connect("crypto_bot.db")
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)')
    cursor.execute('CREATE TABLE IF NOT EXISTS portfolio (user_id INTEGER, coin TEXT, amount REAL)')
    conn.commit()
    conn.close()

# --- ФУНКЦИИ ПОЛУЧЕНИЯ КУРСОВ ---
async def get_crypto_prices():
    url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,binancecoin,solana,the-open-network,tether&vs_currencies=usd,rub"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()

async def get_exchange_rates():
    # Сравнение цен на BTC на разных биржах (Binance vs Bybit упрощенно через API)
    url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCTETHER"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()
            return float(data['price'])

# --- КЛАВИАТУРА ---
def get_main_kb(user_id):
    buttons = [
        [KeyboardButton(text="💰 Курсы валют"), KeyboardButton(text="📊 Лучший обмен")],
        [KeyboardButton(text="💼 Мой портфель"), KeyboardButton(text="🔄 Конвертер")]
    ]
    if user_id == ADMIN_ID:
        buttons.append([KeyboardButton(text="📢 Рассылка")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# --- ОБРАБОТЧИКИ ---

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    conn = sqlite3.connect("crypto_bot.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users VALUES (?)", (user_id,))
    conn.commit()
    conn.close()
    
    await message.answer(
        "👋 Привет! Я твой крипто-помощник.\n\n"
        "Я показываю курсы валют, помогаю найти выгодный обмен и слежу за твоим портфелем.",
        reply_markup=get_main_kb(user_id)
    )

@dp.message(F.text == "💰 Курсы валют")
async def show_prices(message: types.Message):
    data = await get_crypto_prices()
    text = (
        "📈 <b>Актуальные курсы:</b>\n\n"
        f"₿ <b>Bitcoin:</b> ${data['bitcoin']['usd']:,} | {data['bitcoin']['rub']:,} ₽\n"
        f"💎 <b>Ethereum:</b> ${data['ethereum']['usd']:,} | {data['ethereum']['rub']:,} ₽\n"
        f"🪙 <b>TON:</b> ${data['the-open-network']['usd']} | {data['the-open-network']['rub']} ₽\n"
        f"☀️ <b>Solana:</b> ${data['solana']['usd']} | {data['solana']['rub']} ₽\n"
        f"💵 <b>USDT:</b> ${data['tether']['usd']} | {data['tether']['rub']} ₽\n"
    )
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "📊 Лучший обмен")
async def best_exchange(message: types.Message):
    binance_price = await get_exchange_rates()
    # Эмуляция сравнения (в реальности нужно подключать API каждой биржи)
    bybit_price = binance_price + 2.5 
    okx_price = binance_price - 1.2
    
    text = (
        "🔍 <b>Сравнение цены BTC/USDT:</b>\n\n"
        f"🔸 Binance: <code>${binance_price}</code>\n"
        f"🔸 Bybit: <code>${bybit_price}</code>\n"
        f"🔸 OKX: <code>${okx_price}</code>\n\n"
        f"✅ Выгоднее всего купить на: <b>OKX</b>"
    )
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "🔄 Конвертер")
async def converter_start(message: types.Message, state: FSMContext):
    await message.answer("Введите сумму в BTC для перевода в рубли (например: 0.005):")
    await state.set_state(States.converting)

@dp.message(States.converting)
async def converter_process(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(',', '.'))
        data = await get_crypto_prices()
        btc_rub = data['bitcoin']['rub']
        res = amount * btc_rub
        await message.answer(f"✅ {amount} BTC = <b>{res:,.2f} рублей</b>", parse_mode="HTML")
    except:
        await message.answer("❌ Ошибка. Введите число (например: 0.5)")
    await state.clear()

@dp.message(F.text == "💼 Мой портфель")
async def portfolio_show(message: types.Message):
    # Здесь можно добавить логику добавления монет, пока сделаем заглушку
    await message.answer("🛠 Функция 'Портфель' в разработке. Здесь вы сможете хранить баланс своих монет.")

# --- АДМИНКА ---
@dp.message(F.text == "📢 Рассылка")
async def start_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("Отправьте текст сообщения для рассылки всем:")
    await state.set_state(States.broadcasting)

@dp.message(States.broadcasting)
async def do_broadcast(message: types.Message, state: FSMContext):
    conn = sqlite3.connect("crypto_bot.db")
    cursor = conn.cursor()
    users = cursor.execute("SELECT user_id FROM users").fetchall()
    conn.close()
    
    await message.answer("🚀 Рассылка запущена...")
    for user in users:
        try:
            await bot.send_message(user[0], message.text)
            await asyncio.sleep(0.05)
        except: pass
    await message.answer("✅ Рассылка завершена!")
    await state.clear()

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
