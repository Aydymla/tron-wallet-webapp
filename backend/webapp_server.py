import aiosqlite
import asyncio
from fastapi import FastAPI

app = FastAPI()

# === Инициализация базы данных ===
async def init_db():
    async with aiosqlite.connect("wallets.db") as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS wallets (
            user_id INTEGER PRIMARY KEY,
            mnemonic TEXT,
            address TEXT
        )
        """)
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
        )
        """)
        await db.commit()

@app.on_event("startup")
async def on_startup():
    print("[INIT] Creating database if not exists...")
    await init_db()
