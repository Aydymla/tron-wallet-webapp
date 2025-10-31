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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import aiohttp, aiosqlite, os, uvicorn

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://aydymla.github.io"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/wallet/{user_id}")
async def get_wallet(user_id: int):
    async with aiosqlite.connect("wallets.db") as db:
        async with db.execute("SELECT address FROM wallets WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()

    if not row:
        return {"error": "wallet_not_found"}

    address = row[0]
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://api.trongrid.io/v1/accounts/{address}") as resp:
            data = await resp.json()

    acc = data.get("data", [{}])[0]
    trx = acc.get("balance", 0) / 1e6
    energy = acc.get("energy", 0)
    usdt = 0
    for token in acc.get("trc20", []):
        if "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t" in token:
            usdt = float(token["TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"]) / 1e6

    return {"address": address, "trx_balance": trx, "usdt_balance": usdt, "energy": energy}

if __name__ == "__main__":
    uvicorn.run("backend.webapp_server:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
