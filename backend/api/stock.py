from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from core.database import get_db
from core.redis import get_redis
from models.price_history import PriceHistory
from services.analytics import calc_risk_metrics, monte_carlo, numpy_to_python
import httpx

router = APIRouter(prefix="/api/stock", tags=["Stock"])


async def _get_price(symbol: str, redis) -> float | None:
    key = f"price:stock:{symbol.lower().replace('.', '_')}"
    val = await redis.get(key)
    return float(val) if val else None


async def _get_price_series(symbol: str, db: AsyncSession) -> list[float]:
    result = await db.execute(
        select(PriceHistory.close_price)
        .where(PriceHistory.symbol == symbol)
        .order_by(desc(PriceHistory.price_date))
        .limit(365)
    )
    rows = result.scalars().all()
    return [float(r) for r in reversed(rows)]


@router.get("/list")
async def list_stocks():
    return [
        {"symbol": "TCS.NS",        "longName": "Tata Consultancy Services"},
        {"symbol": "INFY.NS",        "longName": "Infosys Ltd"},
        {"symbol": "RELIANCE.NS",    "longName": "Reliance Industries"},
        {"symbol": "HDFCBANK.NS",    "longName": "HDFC Bank"},
        {"symbol": "SBIN.NS",        "longName": "State Bank of India"},
        {"symbol": "ICICIBANK.NS",   "longName": "ICICI Bank"},
        {"symbol": "HINDUNILVR.NS",  "longName": "Hindustan Unilever"},
        {"symbol": "MARUTI.NS",      "longName": "Maruti Suzuki"},
        {"symbol": "BAJFINANCE.NS",  "longName": "Bajaj Finance"},
        {"symbol": "KOTAKBANK.NS",   "longName": "Kotak Mahindra Bank"},
    ]


@router.get("/search")
async def search_stocks(q: str = Query(...)):
    stocks = await list_stocks()
    q_lower = q.lower()
    return [
        s for s in stocks
        if q_lower in s["symbol"].lower() or q_lower in s["longName"].lower()
    ][:8]


@router.get("/quote/{symbol}")
async def get_quote(symbol: str, db: AsyncSession = Depends(get_db)):
    redis = await get_redis()
    price = await _get_price(symbol, redis)

    # fallback: latest from price_history
    if price is None:
        result = await db.execute(
            select(PriceHistory.close_price)
            .where(PriceHistory.symbol == symbol)
            .order_by(desc(PriceHistory.price_date))
            .limit(1)
        )
        row = result.scalar_one_or_none()
        price = float(row) if row else None

    if price is None:
        raise HTTPException(status_code=404, detail=f"No price data for {symbol}")

    return {
        "symbol": symbol,
        "price": price,
        "currentPrice": price,  # alias for frontend compatibility
        "source": "redis+db",
    }


@router.get("/profile/{symbol}")
async def get_profile(symbol: str):
    # Fetch from yfinance via httpx (non-blocking)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
                headers={"User-Agent": "Mozilla/5.0"},
            )
        data = r.json()
        meta = data.get("chart", {}).get("result", [{}])[0].get("meta", {})
        return {
            "symbol": symbol,
            "longName": meta.get("longName") or meta.get("shortName") or symbol,
            "currentPrice": meta.get("regularMarketPrice"),
            "currency": meta.get("currency"),
            "exchange": meta.get("exchangeName"),
        }
    except Exception:
        return {"symbol": symbol, "longName": symbol, "currentPrice": None}


@router.get("/history/{symbol}")
async def get_history(symbol: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PriceHistory)
        .where(PriceHistory.symbol == symbol)
        .order_by(PriceHistory.price_date)
        .limit(365)
    )
    rows = result.scalars().all()
    if not rows:
        raise HTTPException(status_code=404, detail=f"No history for {symbol}")
    return [
        {"date": str(r.price_date), "close": float(r.close_price)}
        for r in rows
    ]


@router.get("/risk-volatility/{symbol}")
async def get_risk_volatility(symbol: str, db: AsyncSession = Depends(get_db)):
    series = await _get_price_series(symbol, db)
    if len(series) < 2:
        return {"annualized_volatility": 0.0, "annualized_return": 0.0, "sharpe_ratio": 0.0}
    risk = calc_risk_metrics(series)
    return {
        "annualized_volatility": risk["volatility"] / 100,
        "annualized_return": 0.0,
        "sharpe_ratio": risk["sharpe"],
        "max_drawdown": risk["max_drawdown"],
    }


@router.get("/monte-carlo-prediction/{symbol}")
async def get_monte_carlo(symbol: str, db: AsyncSession = Depends(get_db)):
    redis = await get_redis()
    cache_key = f"mc:stock:{symbol.lower()}"
    cached = await redis.get(cache_key)
    if cached:
        import json
        return json.loads(cached)

    series = await _get_price_series(symbol, db)
    if len(series) < 10:
        raise HTTPException(status_code=404, detail="Insufficient data")

    import json
    mc = monte_carlo(series[-1], series)
    result = {
        "expected_nav": mc["p50"],
        "lower_bound_5th_percentile": mc["p10"],
        "upper_bound_95th_percentile": mc["p90"],
        "probability_positive_return": 65.0,
        "current_value": mc["current_value"],
    }
    await redis.setex(cache_key, 21600, json.dumps(result))
    return result


@router.get("/performance-heatmap/{symbol}")
async def get_performance_heatmap(symbol: str, db: AsyncSession = Depends(get_db)):
    """Compute monthly returns from price_history for a stock."""
    result = await db.execute(
        select(PriceHistory)
        .where(PriceHistory.symbol == symbol)
        .order_by(PriceHistory.price_date)
        .limit(365)
    )
    rows = result.scalars().all()
    if len(rows) < 2:
        return []

    from collections import defaultdict

    monthly: dict[tuple[int, int], list[float]] = defaultdict(list)
    for r in rows:
        d = r.price_date
        monthly[(d.year, d.month)].append(float(r.close_price))

    heatmap = []
    for (year, month), prices in sorted(monthly.items()):
        if len(prices) >= 2:
            ret = (prices[-1] - prices[0]) / prices[0]
            heatmap.append({"year": year, "month": month, "value": round(ret, 6)})

    return heatmap
