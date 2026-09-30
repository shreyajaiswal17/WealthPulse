import yfinance as yf
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from models.price_history import PriceHistory

STOCK_SYMBOLS = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS",
                 "ICICIBANK.NS", "WIPRO.NS", "SBIN.NS", "BAJFINANCE.NS"]

async def backfill_stock_history(db: AsyncSession):
    print("🔄 Backfilling stock price history...")
    for symbol in STOCK_SYMBOLS:
        try:
            df = yf.download(symbol, period="1y", interval="1d",
                             progress=False, auto_adjust=True)
            if df.empty:
                print(f"⚠️ No data for {symbol}")
                continue

            rows = []
            for dt, row in df.iterrows():
                close = row["Close"]
                price = float(close.iloc[0]) if hasattr(close, 'iloc') else float(close)
                rows.append({
                    "symbol": symbol,
                    "asset_type": "stock",
                    "price_date": dt.date(),
                    "close_price": price,
                })

            stmt = insert(PriceHistory).values(rows).on_conflict_do_nothing()
            await db.execute(stmt)
            await db.commit()
            print(f"✅ {symbol} — {len(rows)} rows inserted")

        except Exception as e:
            print(f"⚠️ Backfill error for {symbol}: {e}")
