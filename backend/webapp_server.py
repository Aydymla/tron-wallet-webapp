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
