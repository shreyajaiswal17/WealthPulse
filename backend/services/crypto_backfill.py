import asyncio
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from models.price_history import PriceHistory
from datetime import datetime

CRYPTO_COINS = [
    {"coin_id": "bitcoin",      "symbol": "btcusdt"},
    {"coin_id": "ethereum",     "symbol": "ethusdt"},
    {"coin_id": "solana",       "symbol": "solusdt"},
    {"coin_id": "binancecoin",  "symbol": "bnbusdt"},
    {"coin_id": "cardano",      "symbol": "adausdt"},
    {"coin_id": "dogecoin",     "symbol": "dogeusdt"},
]

COINGECKO_BASE = "https://api.coingecko.com/api/v3"


async def backfill_crypto_history(db: AsyncSession):
    print("🔄 Backfilling crypto price history...")
    async with httpx.AsyncClient() as client:
        for coin in CRYPTO_COINS:
            try:
                # Check if already seeded
                from sqlalchemy import select, func
                from models.price_history import PriceHistory as PH
                result = await db.execute(
                    select(func.count()).where(
                        PH.symbol == coin["symbol"],
                        PH.asset_type == "crypto"
                    )
                )
                count = result.scalar()
                if count >= 30:
                    print(f"⏭️  {coin['symbol']} — skipped (already seeded with {count} rows)")
                    continue

                r = await client.get(
                    f"{COINGECKO_BASE}/coins/{coin['coin_id']}/market_chart",
                    params={"vs_currency": "usd", "days": "365"},
                    timeout=20,
                )
                if r.status_code != 200:
                    print(f"⚠️  CoinGecko error for {coin['coin_id']}: {r.status_code}")
                    continue

                prices = r.json().get("prices", [])

                rows = []
                seen_dates = set()
                for ts_ms, price in prices:
                    date = datetime.utcfromtimestamp(ts_ms / 1000).date()
                    if date in seen_dates:
                        continue
                    seen_dates.add(date)
                    rows.append({
                        "symbol": coin["symbol"],
                        "asset_type": "crypto",
                        "price_date": date,
                        "close_price": float(price),
                    })

                if rows:
                    stmt = insert(PriceHistory).values(rows).on_conflict_do_nothing()
                    await db.execute(stmt)
                    await db.commit()
                    print(f"✅ {coin['symbol']} — {len(rows)} rows inserted")

                await asyncio.sleep(2)  # 2s between each coin to avoid CoinGecko 429

            except Exception as e:
                print(f"⚠️  Crypto backfill error for {coin['coin_id']}: {e}")
