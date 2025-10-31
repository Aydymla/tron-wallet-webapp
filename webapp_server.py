from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import aiosqlite
import uvicorn
import os

app = FastAPI()

# Разрешаем GitHub Pages
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://Aydymla.github.io"],  # важно!
    allow_credentials=True,
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
    # Загружаем баланс из TronGrid
    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://api.trongrid.io/v1/accounts/{address}") as resp:
            data = await resp.json()

    acc = data.get("data", [{}])[0]
    trx = acc.get("balance", 0) / 1e6
    energy = acc.get("energy", 0)
    tokens = acc.get("trc20", [])
    usdt = 0
    for t in tokens:
        if "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t" in t:
            usdt = float(t["TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"]) / 1e6
            break

    return {
        "address": address,
        "trx_balance": trx,
        "usdt_balance": usdt,
        "energy": energy
    }

if __name__ == "__main__":
    uvicorn.run("webapp_server:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
