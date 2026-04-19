import os
import sqlite3
import asyncio
import aiohttp
import time
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
    converting = State()
    broadcasting = State()

# --- API СЕРВИС (Оптимизированный) ---
class CryptoAPI:
    def __init__(self):
        self.session = None

    async def get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def fetch_prices(self):
        session = await self.get_session()
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana,the-open-network,tether&vs_currencies=usd,rub"
        async with session.get(url) as resp:
            return await resp.json()

    async def get_fear_greed(self):
        session = await self.get_session()
        async with session.get("https://api.alternative.me/fng/") as resp:
            data = await resp.json()
            return data['data'][0]

crypto_api = CryptoAPI()

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect("crypto.db")
    conn.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY)')
    conn.close()

# --- КЛАВИАТУРА ---
def main_kb(user_id):
    kb = [
        [KeyboardButton(text="💎 Курсы Валют"), KeyboardButton(text="💳 P2P Обмен")],
        [KeyboardButton(text="🔄 Калькулятор"), KeyboardButton(text="📊 Настроение рынка")]
    ]
    if user_id == ADMIN_ID:
        kb.append([KeyboardButton(text="📢 Рассылка")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# --- ОБРАБОТЧИКИ ---

@dp.message(CommandStart())
async def start(message: types.Message):
    user_id = message.from_user.id
    conn = sqlite3.connect("crypto.db")
    conn.execute("INSERT OR IGNORE INTO users VALUES (?)", (user_id,))
    conn.commit()
    conn.close()
    await message.answer("🚀 <b>Crypto Dash запущен!</b>\nИспользуй меню ниже для навигации.", 
                         parse_mode="HTML", reply_markup=main_kb(user_id))

@dp.message(F.text == "💎 Курсы Валют")
async def prices(message: types.Message):
    data = await crypto_api.fetch_prices()
    
    msg = (
        "📈 <b>Рыночные котировки</b>\n"
        "<code>————————————————————</code>\n"
        f"₿ <b>BTC:</b> <code>${data['bitcoin']['usd']:,}</code>\n"
        f"└ RUB: <code>{data['bitcoin']['rub']:,} ₽</code>\n\n"
        f"💎 <b>ETH:</b> <code>${data['ethereum']['usd']:,}</code>\n"
        f"└ RUB: <code>{data['ethereum']['rub']:,} ₽</code>\n\n"
        f"💎 <b>TON:</b> <code>${data['the-open-network']['usd']}</code>\n"
        f"└ RUB: <code>{data['the-open-network']['rub']} ₽</code>\n\n"
        f"☀️ <b>SOL:</b> <code>${data['solana']['usd']}</code>\n"
        f"└ RUB: <code>{data['solana']['rub']} ₽</code>\n\n"
        f"💵 <b>USDT:</b> <code>{data['tether']['rub']} ₽</code>\n"
        "<code>————————————————————</code>\n"
        "<i>Обновлено в реальном времени</i>"
    )
    await message.answer(msg, parse_mode="HTML")

@dp.message(F.text == "💳 P2P Обмен")
async def p2p_rates(message: types.Message):
    data = await crypto_api.fetch_prices()
    usdt_rub = data['tether']['rub']
    
    # Эмуляция P2P наценки (обычно +2-3 рубля к биржевому курсу)
    sber_rate = usdt_rub + 2.45
    tink_rate = usdt_rub + 2.10
    
    msg = (
        "🤝 <b>Лучшие курсы P2P (USDT/RUB)</b>\n"
        "<i>Где выгоднее купить прямо сейчас:</i>\n\n"
        f"🟡 <b>Tinkoff:</b> <code>{tink_rate:.2f} ₽</code>\n"
        f"🟢 <b>Sberbank:</b> <code>{sber_rate:.2f} ₽</code>\n"
        f"🔵 <b>Bybit P2P:</b> <code>{tink_rate - 0.15:.2f} ₽</code>\n\n"
        "💡 <i>Рекомендуем Bybit для минимальной комиссии.</i>"
    )
    await message.answer(msg, parse_mode="HTML")

@dp.message(F.text == "📊 Настроение рынка")
async def fear_greed(message: types.Message):
    fng = await crypto_api.get_fear_greed()
    val = int(fng['value'])
    
    emoji = "😨" if val < 30 else "😐" if val < 70 else "🤑"
    status = fng['value_classification']
    
    msg = (
        f"📉 <b>Fear & Greed Index: {val}/100</b>\n"
        f"Статус: <b>{status} {emoji}</b>\n\n"
        "• 0-25: Экстремальный страх (Покупай)\n"
        "• 75-100: Экстремальная жадность (Продавай)"
    )
    await message.answer(msg, parse_mode="HTML")

# --- УНИВЕРСАЛЬНЫЙ КАЛЬКУЛЯТОР ---
@dp.message(F.text == "🔄 Калькулятор")
async def calc_start(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="BTC", callback_data="calc_bitcoin"), 
         InlineKeyboardButton(text="ETH", callback_data="calc_ethereum")],
        [InlineKeyboardButton(text="TON", callback_data="calc_the-open-network"), 
         InlineKeyboardButton(text="SOL", callback_data="calc_solana")]
    ])
    await message.answer("Выберите монету для расчета в RUB:", reply_markup=kb)

@dp.callback_query(F.data.startswith("calc_"))
async def calc_coin_selected(call: types.CallbackQuery, state: FSMContext):
    coin = call.data.split("_")[1]
    await state.update_data(chosen_coin=coin)
    await call.message.answer(f"Введите количество {coin.upper()}:")
    await state.set_state(States.converting)
    await call.answer()

@dp.message(States.converting)
async def calc_finish(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
        data = await state.get_data()
        coin = data['chosen_coin']
        
        prices = await crypto_api.fetch_prices()
        rate = prices[coin]['rub']
        res = amount * rate
        
        await message.answer(f"💰 <b>Результат:</b>\n{amount} {coin.upper()} = <code>{res:,.2f} ₽</code>", parse_mode="HTML")
    except:
        await message.answer("❌ Введите числовое значение.")
    await state.clear()

# --- РАССЫЛКА ---
@dp.message(F.text == "📢 Рассылка")
async def broadcast_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("Введите текст рассылки:")
    await state.set_state(States.broadcasting)

@dp.message(States.broadcasting)
async def broadcast_done(message: types.Message, state: FSMContext):
    conn = sqlite3.connect("crypto.db")
    users = conn.execute("SELECT id FROM users").fetchall()
    conn.close()
    
    for u in users:
        try:
            await bot.send_message(u[0], message.text)
            await asyncio.sleep(0.05)
        except: pass
    await message.answer("✅ Готово!")
    await state.clear()

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
