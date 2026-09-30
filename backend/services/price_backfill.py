import httpx
import yfinance as yf
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import select, func
from models.price_history import PriceHistory

COIN_ID_TO_SYMBOL = {
    "bitcoin":     "btcusdt",
    "ethereum":    "ethusdt",
    "solana":      "solusdt",
    "binancecoin": "bnbusdt",
    "cardano":     "adausdt",
    "dogecoin":    "dogeusdt",
}

COINGECKO_BASE = "https://api.coingecko.com/api/v3"


async def _count_rows(symbol: str, asset_type: str, db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count()).where(
            PriceHistory.symbol == symbol,
            PriceHistory.asset_type == asset_type,
        )
    )
    return result.scalar()


async def ensure_stock_history(symbol: str, db: AsyncSession):
    count = await _count_rows(symbol, "stock", db)
    if count >= 30:
        return
    print(f"🔄 Lazy backfill: stock {symbol}")
    try:
        df = yf.download(symbol, period="1y", interval="1d",
                         progress=False, auto_adjust=True)
        if df.empty:
            print(f"⚠️  No yfinance data for {symbol}")
            return
        rows = []
        for dt, row in df.iterrows():
            close = row["Close"]
            price = float(close.iloc[0]) if hasattr(close, "iloc") else float(close)
            rows.append({
                "symbol": symbol,
                "asset_type": "stock",
                "price_date": dt.date(),
                "close_price": price,
            })
        stmt = insert(PriceHistory).values(rows).on_conflict_do_nothing()
        await db.execute(stmt)
        await db.commit()
        print(f"✅ Lazy backfill: {symbol} — {len(rows)} rows")
    except Exception as e:
        print(f"⚠️  Lazy backfill error for stock {symbol}: {e}")


async def ensure_mf_history(scheme_code: str, db: AsyncSession):
    count = await _count_rows(scheme_code, "mutualfund", db)
    if count >= 30:
        return
    print(f"🔄 Lazy backfill: MF {scheme_code}")
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"https://api.mfapi.in/mf/{scheme_code}", timeout=15
            )
        if r.status_code != 200:
            return
        nav_history = r.json().get("data", [])
        rows = []
        for entry in nav_history:
            try:
                date_val = datetime.strptime(entry["date"], "%d-%m-%Y").date()
                nav = float(entry["nav"])
                rows.append({
                    "symbol": scheme_code,
                    "asset_type": "mutualfund",
                    "price_date": date_val,
                    "close_price": nav,
                })
            except Exception:
                continue
        if rows:
            stmt = insert(PriceHistory).values(rows).on_conflict_do_nothing()
            await db.execute(stmt)
            await db.commit()
            print(f"✅ Lazy backfill: MF {scheme_code} — {len(rows)} rows")
    except Exception as e:
        print(f"⚠️  Lazy backfill error for MF {scheme_code}: {e}")


async def ensure_crypto_history(coin_id: str, db: AsyncSession):
    symbol = COIN_ID_TO_SYMBOL.get(coin_id)
    if not symbol:
        print(f"⚠️  Unknown coin_id for lazy backfill: {coin_id}")
        return
    count = await _count_rows(symbol, "crypto", db)
    if count >= 30:
        return
    print(f"🔄 Lazy backfill: crypto {coin_id}")
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{COINGECKO_BASE}/coins/{coin_id}/market_chart",
                params={"vs_currency": "usd", "days": "365"},
                timeout=20,
            )
        if r.status_code != 200:
            return
        prices = r.json().get("prices", [])
        rows = []
        seen_dates = set()
        for ts_ms, price in prices:
            date = datetime.utcfromtimestamp(ts_ms / 1000).date()
            if date in seen_dates:
                continue
            seen_dates.add(date)
            rows.append({
                "symbol": symbol,
                "asset_type": "crypto",
                "price_date": date,
                "close_price": float(price),
            })
        if rows:
            stmt = insert(PriceHistory).values(rows).on_conflict_do_nothing()
            await db.execute(stmt)
            await db.commit()
            print(f"✅ Lazy backfill: crypto {coin_id} — {len(rows)} rows")
    except Exception as e:
        print(f"⚠️  Lazy backfill error for crypto {coin_id}: {e}")
