import os
import asyncio
import logging
import aiosqlite
import aiohttp
import hashlib
from datetime import datetime
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup

from tronpy import Tron
from tronpy.keys import PrivateKey
from tronpy.providers import HTTPProvider
from bip_utils import Bip39MnemonicGenerator, Bip39SeedGenerator, Bip44, Bip44Coins, Bip44Changes



load_dotenv()
logging.basicConfig(level=logging.INFO)
logging.getLogger("aiogram").setLevel(logging.DEBUG)


BOT_TOKEN = os.getenv("BOT_TOKEN")
TRON_API_KEY = os.getenv("TRON_PRO_API_KEY")
USDT_CONTRACT = os.getenv("USDT_CONTRACT_ADDRESS")
AML_ID = os.getenv("AML_ACCESS_ID")
AML_KEY = os.getenv("AML_ACCESS_KEY")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(storage=MemoryStorage())

client = Tron(provider=HTTPProvider(api_key=TRON_API_KEY))
contract = client.get_contract(USDT_CONTRACT)

# === FSM для действий с адресом ===
class WalletAction(StatesGroup):
    waiting_for_choice = State()
    waiting_for_amount = State()
    confirm = State()

# === База данных ===
async def init_db():
    async with aiosqlite.connect("wallets.db") as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS wallets (
            user_id INTEGER PRIMARY KEY,
            mnemonic TEXT,
            address TEXT
        )""")
        await db.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            tx_hash TEXT,
            type TEXT,
            from_address TEXT,
            to_address TEXT,
            amount REAL,
            timestamp TEXT,
            tronscan_url TEXT
        )""")
        await db.commit()


# === Утилиты TRON ===
def create_wallet():
    mnemonic_obj = Bip39MnemonicGenerator().FromWordsNumber(12)
    mnemonic = str(mnemonic_obj)  # ✅ превращаем в обычную строку
    seed = Bip39SeedGenerator(mnemonic).Generate()
    bip44 = (
        Bip44.FromSeed(seed, Bip44Coins.TRON)
        .Purpose()
        .Coin()
        .Account(0)
        .Change(Bip44Changes.CHAIN_EXT)
        .AddressIndex(0)
    )
    private_key = bip44.PrivateKey().Raw().ToBytes()
    address = bip44.PublicKey().ToAddress()
    return mnemonic, address, private_key


# === /wallet ===
@dp.message(Command("wallet"))
async def show_wallet_balance(message: types.Message):
    user_id = message.from_user.id
    logging.info(f"[DEBUG] Команда /wallet от пользователя {user_id}")

    try:
        async with aiosqlite.connect("wallets.db") as db:
            async with db.execute("SELECT address FROM wallets WHERE user_id = ?", (user_id,)) as cur:
                row = await cur.fetchone()

        if not row:
            await message.answer("⚠️ У вас ещё нет кошелька. Используйте /start, чтобы создать.")
            return

        address = row[0]
        logging.info(f"[DEBUG] Адрес найден: {address}")

        async with aiohttp.ClientSession() as session:
            trx_url = f"https://api.trongrid.io/v1/accounts/{address}"
            async with session.get(trx_url) as resp:
                acc_data = await resp.json()
                logging.debug(f"[DEBUG] Ответ от TronGrid: {acc_data}")

        # Проверяем, что TronGrid вернул хоть что-то
        if not acc_data.get("data"):
            await message.answer(
                f"💼 <b>Ваш TRON кошелёк</b>\n\n"
                f"<b>Адрес:</b> <code>{address}</code>\n"
                f"💰 Баланс TRX: 0.0000\n"
                f"💵 Баланс USDT: 0.00\n"
                f"⚡ Energy: 0\n"
                f"🔋 Bandwidth: 0\n\n"
                f"🆕 Новый адрес, пока без активности.\n"
                f"<a href='https://tronscan.org/#/address/{address}'>🔗 Смотреть на Tronscan</a>"
            )
            return

        account = acc_data["data"][0]
        trx_balance = account.get("balance", 0) / 1e6
        energy = account.get("energy", 0)
        bandwidth = account.get("free_net_usage", 0)

        usdt_contract = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
        tokens = account.get("trc20", [])
        usdt_balance = 0
        for token in tokens:
            if usdt_contract in token:
                usdt_balance = float(token[usdt_contract]) / 1e6
                break

        await message.answer(
            f"💼 <b>Ваш TRON кошелёк</b>\n\n"
            f"<b>🏦 Адрес:</b> <code>{address}</code>\n"
            f"<b>💰 TRX:</b> {trx_balance:.4f}\n"
            f"<b>💵 USDT:</b> {usdt_balance:.2f}\n"
            f"<b>⚡ Energy:</b> {energy}\n"
            f"<b>🔋 Bandwidth:</b> {bandwidth}\n\n"
            f"<a href='https://tronscan.org/#/address/{address}'>🔗 Смотреть в Tronscan</a>"
        )

    except Exception as e:
        logging.error(f"[ERROR /wallet] {e}", exc_info=True)
        await message.answer("⚠️ Ошибка при получении данных. Попробуйте позже.")



def get_private_key(mnemonic):
    seed = Bip39SeedGenerator(mnemonic).Generate()
    bip44 = Bip44.FromSeed(seed, Bip44Coins.TRON).Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT).AddressIndex(0)
    return PrivateKey(bip44.PrivateKey().Raw().ToBytes())


@dp.message(Command("app"))
async def open_webapp(message: types.Message):
    webapp_url = "https://yourdomain.com/"  # или http://127.0.0.1:8000/
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌐 Открыть кошелёк", web_app=types.WebAppInfo(url=webapp_url))]
        ]
    )
    await message.answer("Откройте WebApp:", reply_markup=keyboard)
    

# === /start ===
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id

    async with aiosqlite.connect("wallets.db") as db:
        async with db.execute("SELECT address FROM wallets WHERE user_id = ?", (user_id,)) as cur:
            existing_wallet = await cur.fetchone()

    if existing_wallet:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Пересоздать", callback_data="recreate_wallet"),
                InlineKeyboardButton(text="❌ Оставить старый", callback_data="cancel_wallet_action")
            ]
        ])
        await message.answer(
            "👋 Привет!\n"
            "У вас уже есть созданный кошелёк.\n"
            "Хотите пересоздать его или оставить старый?",
            reply_markup=keyboard
        )
        return

    # Если кошелька нет — создаём сразу
    await create_new_wallet(message, user_id)


# === Подтверждение пересоздания кошелька ===
@dp.callback_query(F.data == "recreate_wallet")
async def confirm_recreate_wallet(callback: types.CallbackQuery):
    user_id = callback.from_user.id

    async with aiosqlite.connect("wallets.db") as db:
        await db.execute("DELETE FROM wallets WHERE user_id = ?", (user_id,))
        await db.commit()

    await create_new_wallet(callback.message, user_id)
    await callback.answer()


@dp.callback_query(F.data == "cancel_wallet_action")
async def cancel_wallet_action(callback: types.CallbackQuery):
    await callback.message.edit_text("❌ Действие отменено. Старый кошелёк сохранён.")
    await callback.answer()


# === Вынесенная функция для создания нового кошелька ===
async def create_new_wallet(message: types.Message, user_id: int):
    mnemonic, address, _ = create_wallet()

    async with aiosqlite.connect("wallets.db") as db:
        await db.execute(
            "INSERT INTO wallets (user_id, mnemonic, address) VALUES (?, ?, ?)",
            (user_id, mnemonic, address)
        )
        await db.commit()

    await message.answer(
        f"✅ <b>Ваш новый TRON-кошелёк создан!</b>\n\n"
        f"<b>🔑 Seed фраза:</b>\n<tg-spoiler>{mnemonic}</tg-spoiler>\n\n"
        f"<b>💼 Адрес:</b> <code>{address}</code>\n\n"
        f"⚠️ Сохраните сид-фразу — без неё восстановление невозможно."
    )

# === Мониторинг USDT ===
async def check_incoming():
    while True:
        try:
            async with aiosqlite.connect("wallets.db") as db:
                async with db.execute("SELECT user_id, address FROM wallets") as cur:
                    wallets = await cur.fetchall()

            for user_id, address in wallets:
                url = f"https://api.trongrid.io/v1/accounts/{address}/transactions/trc20?limit=5"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        data = await resp.json()

                for tx in data.get("data", []):
                    if tx.get("to") == address and tx["token_info"]["address"] == USDT_CONTRACT:
                        txid = tx["transaction_id"]
                        amount = int(tx["value"]) / 1e6
                        sender = tx["from"]

                        # Проверяем дубликат
                        async with aiosqlite.connect("wallets.db") as db:
                            async with db.execute("SELECT 1 FROM transactions WHERE tx_hash = ?", (txid,)) as c:
                                if await c.fetchone():
                                    continue

                            await db.execute("""
                            INSERT INTO transactions (user_id, tx_hash, type, from_address, to_address, amount, timestamp, tronscan_url)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """, (user_id, txid, "incoming", sender, address, amount,
                                  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                  f"https://tronscan.org/#/transaction/{txid}"))
                            await db.commit()

                        aml = await check_aml(sender)
                        risk = aml.get("risk_score_level", "unknown").upper()
                        await bot.send_message(
                            chat_id=user_id,
                            text=(
                                f"📥 <b>Получено {amount} USDT!</b>\n"
                                f"<b>От:</b> <code>{sender}</code>\n"
                                f"<b>Риск AML:</b> {risk}\n"
                                f"<b>Хеш:</b> <code>{txid}</code>\n"
                                f"<a href='https://tronscan.org/#/transaction/{txid}'>🔗 Смотреть в Tronscan</a>"
                            )
                        )
            await asyncio.sleep(15)
        except Exception as e:
            logging.error(e)
            await asyncio.sleep(10)


# === Проверка AML ===
async def check_aml(address: str):
    token_str = f"{address}:{AML_KEY}:{AML_ID}"
    token = hashlib.md5(token_str.encode()).hexdigest()
    data = {"hash": address, "asset": "TRX", "accessId": AML_ID, "token": token, "locale": "en_US", "flow": "lite"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post("https://extrnlapiendpoint.silencatech.com/", data=data) as resp:
                return await resp.json()
    except:
        return {"risk_score_level": "unknown"}


# === Авто-обработка сообщений с адресом TRON ===

@dp.message(StateFilter(WalletAction.waiting_for_amount), F.text)
async def handle_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.strip())
        await state.update_data(amount=amount)

        data = await state.get_data()
        addr = data["address"]

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да", callback_data="confirm_yes"),
                InlineKeyboardButton(text="❌ Нет", callback_data="confirm_no")
            ]
        ])

        await state.set_state(WalletAction.confirm)
        await message.answer(
            f"Вы уверены, что хотите отправить <b>{amount} USDT</b> на адрес <code>{addr}</code>?",
            reply_markup=keyboard
        )

        logging.info(f"[FSM] Пользователь {message.from_user.id} ввел сумму: {amount} USDT")

    except ValueError:
        await message.answer("❌ Введите корректное число (например: 12.5)")

@dp.message(F.text)
async def handle_tron_address(message: Message, state: FSMContext):
    text = message.text.strip()

    # Проверяем, похоже ли сообщение на TRON-адрес
    if not (text.startswith("T") and len(text) == 34):
        return  # Игнорируем всё остальное

    await state.update_data(address=text)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🚀 Отправить USDT", callback_data="send_usdt"),
            InlineKeyboardButton(text="🧭 Проверить AML", callback_data="check_aml")
        ]
    ])

    await message.answer(
        f"Вы хотите отправить USDT на адрес <code>{text}</code> или проверить AML?",
        reply_markup=keyboard
    )


# === Обработка нажатия на inline-кнопки ===
@dp.callback_query(F.data == "check_aml")
async def handle_check_aml_callback(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    addr = data.get("address")

    if not addr:
        await callback.answer("⚠️ Адрес не найден, отправьте снова.")
        return

    aml = await check_aml(addr)
    risk = aml.get("risk_score_level", "unknown").upper()
    await callback.message.edit_text(
        f"🧾 Проверка AML для <code>{addr}</code>:\nРиск: <b>{risk}</b>"
    )
    await state.clear()
    await callback.answer()


@dp.callback_query(F.data == "send_usdt")
async def handle_send_usdt_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(WalletAction.waiting_for_amount)

    logging.info(f"[DEBUG] Установлено состояние: {await state.get_state()}")

    await callback.message.edit_text("💰 Введите сумму для отправки (в USDT):")
    await callback.answer()


@dp.callback_query(F.data.in_(["confirm_yes", "confirm_no"]))
async def handle_confirmation(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_id = callback.from_user.id
    addr, amount = data["address"], data["amount"]

    if callback.data == "confirm_no":
        await callback.message.edit_text("❌ Отправка отменена.")
        await state.clear()
        await callback.answer()
        return

    # === Отправка транзакции ===
    async with aiosqlite.connect("wallets.db") as db:
        async with db.execute("SELECT mnemonic, address FROM wallets WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()

    if not row:
        await callback.message.edit_text("⚠️ У вас нет созданного кошелька. Сначала используйте /wallet.")
        await state.clear()
        await callback.answer()
        return

    mnemonic, from_address = row
    priv = get_private_key(mnemonic)
    balance = contract.functions.balanceOf(from_address)

    if balance < amount * 1e6:
        await callback.message.edit_text("❌ Недостаточно средств.")
        await state.clear()
        await callback.answer()
        return

    txn = (
        contract.functions.transfer(addr, int(amount * 1e6))
        .with_owner(from_address)
        .fee_limit(100_000_000)
        .build()
        .sign(priv)
    )
    result = txn.broadcast().wait()
    txid = result["id"]

    async with aiosqlite.connect("wallets.db") as db:
        await db.execute("""
            INSERT INTO transactions (user_id, tx_hash, type, from_address, to_address, amount, timestamp, tronscan_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, txid, "outgoing", from_address, addr, amount,
              datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
              f"https://tronscan.org/#/transaction/{txid}"))
        await db.commit()

    await callback.message.edit_text(
        f"✅ Отправлено {amount} USDT\n🔗 <a href='https://tronscan.org/#/transaction/{txid}'>Смотреть в Tronscan</a>"
    )

    await state.clear()
    await callback.answer("✅ Отправлено успешно!")



# === Запуск ===
async def main():
    await init_db()
    asyncio.create_task(check_incoming())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
