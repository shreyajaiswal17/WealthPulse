import json
import numpy as np
import pandas as pd
import yfinance as yf
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.database import get_db
from core.redis import get_redis
from models.price_history import PriceHistory
from services.price_backfill import ensure_stock_history

router = APIRouter(prefix="/api/stock", tags=["Stock Compat"])

POPULAR_STOCKS = [
    {"symbol": "RELIANCE.NS", "name": "Reliance Industries"},
    {"symbol": "TCS.NS",      "name": "Tata Consultancy Services"},
    {"symbol": "INFY.NS",     "name": "Infosys Ltd"},
    {"symbol": "HDFCBANK.NS", "name": "HDFC Bank"},
    {"symbol": "ICICIBANK.NS","name": "ICICI Bank"},
    {"symbol": "WIPRO.NS",    "name": "Wipro Ltd"},
    {"symbol": "SBIN.NS",     "name": "State Bank of India"},
    {"symbol": "BAJFINANCE.NS","name": "Bajaj Finance"},
    {"symbol": "HINDUNILVR.NS","name": "Hindustan Unilever"},
    {"symbol": "MARUTI.NS",   "name": "Maruti Suzuki"},
    {"symbol": "LT.NS",       "name": "Larsen & Toubro"},
    {"symbol": "ITC.NS",      "name": "ITC Ltd"},
    {"symbol": "AXISBANK.NS", "name": "Axis Bank"},
    {"symbol": "BHARTIARTL.NS","name": "Bharti Airtel"},
    {"symbol": "KOTAKBANK.NS","name": "Kotak Mahindra Bank"},
    {"symbol": "AAPL",        "name": "Apple Inc"},
    {"symbol": "GOOGL",       "name": "Alphabet Inc"},
    {"symbol": "MSFT",        "name": "Microsoft Corp"},
    {"symbol": "TSLA",        "name": "Tesla Inc"},
    {"symbol": "NVDA",        "name": "NVIDIA Corp"},
]


async def _get_price_series(symbol: str, db: AsyncSession, redis) -> list[dict]:
    """Returns [{price_date, close_price}] from pricehistory, triggers backfill if needed."""
    cache_key = f"pseries:stock:{symbol.lower().replace('.', '_')}"
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    result = await db.execute(
        select(PriceHistory)
        .where(PriceHistory.symbol == symbol, PriceHistory.asset_type == "stock")
        .order_by(PriceHistory.price_date)
        .limit(365)
    )
    rows = result.scalars().all()

    if len(rows) < 30:
        await ensure_stock_history(symbol, db)
        result = await db.execute(
            select(PriceHistory)
            .where(PriceHistory.symbol == symbol, PriceHistory.asset_type == "stock")
            .order_by(PriceHistory.price_date)
            .limit(365)
        )
        rows = result.scalars().all()

    series = [{"date": str(r.price_date), "close": float(r.close_price)} for r in rows]
    if series:
        await redis.setex(cache_key, 1800, json.dumps(series))
    return series


def _compute_analytics(series: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(series)
    df["date"] = pd.to_datetime(df["date"])
    df["returns"] = df["close"].pct_change()
    df["ma20"] = df["close"].rolling(window=20).mean()
    df["ma50"] = df["close"].rolling(window=50).mean()
    return df


def _risk_metrics(df: pd.DataFrame) -> dict:
    returns = df["returns"].dropna()
    ann_vol = float(returns.std() * (252 ** 0.5))
    ann_ret = float((returns.mean() + 1) ** 252 - 1)
    sharpe = float((ann_ret - 0.06) / ann_vol) if ann_vol > 0 else 0.0
    returns_list = [
        {"date": str(row["date"])[:10], "returns": float(row["returns"])}
        for _, row in df.iterrows()
        if not pd.isna(row["returns"])
    ]
    return {
        "annualized_volatility": ann_vol,
        "annualized_return": ann_ret,
        "sharpe_ratio": sharpe,
        "returns": returns_list,
    }


def _monte_carlo(df: pd.DataFrame) -> dict:
    returns = df["returns"].dropna()
    mu, sigma = float(returns.mean()), float(returns.std())
    last_price = float(df["close"].iloc[-1])
    num_simulations, days = 1000, 252
    sims = np.zeros((num_simulations, days))
    sims[:, 0] = last_price
    for t in range(1, days):
        sims[:, t] = sims[:, t - 1] * (1 + np.random.normal(mu, sigma, num_simulations))
    return {
        "expected_price": float(np.mean(sims[:, -1])),
        "probability_positive_return": float(np.mean(sims[:, -1] > last_price) * 100),
        "lower_bound_5th_percentile": float(np.percentile(sims[:, -1], 5)),
        "upper_bound_95th_percentile": float(np.percentile(sims[:, -1], 95)),
        "last_price": last_price,
    }


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/search")
async def search_stock(symbol: str = Query(...), redis=Depends(get_redis)):
    cache_key = f"search:stock:{symbol.lower().replace('.', '_')}"
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)
    try:
        info = yf.Ticker(symbol).info
        result = {
            "found": bool(info and info.get("regularMarketPrice")),
            "symbol": symbol,
            "longName": info.get("longName"),
            "exchange": info.get("exchange"),
            "sector": info.get("sector"),
        }
        await redis.setex(cache_key, 3600, json.dumps(result))
        return result
    except Exception:
        return {"found": False, "symbol": symbol}


@router.get("/search-stocks")
async def search_stocks(q: str = Query(...)):
    q_lower = q.lower()
    return [
        s for s in POPULAR_STOCKS
        if q_lower in s["name"].lower() or q_lower in s["symbol"].lower()
    ][:8]


@router.get("/list")
async def list_stocks(redis=Depends(get_redis)):
    cached = await redis.get("stock:list")
    if cached:
        return json.loads(cached)
    result = [
        {"symbol": s["symbol"], "longName": s["name"]}
        for s in POPULAR_STOCKS
    ]
    await redis.setex("stock:list", 3600, json.dumps(result))
    return result


@router.get("/profile/{symbol}")
async def get_profile(symbol: str, redis=Depends(get_redis)):
    cache_key = f"profile:stock:{symbol.lower().replace('.', '_')}"
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)
    try:
        info = yf.Ticker(symbol).info
        result = {
            "symbol": symbol,
            "longName": info.get("longName"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "website": info.get("website"),
            "summary": info.get("longBusinessSummary", ""),
            "marketCap": info.get("marketCap"),
            "regularMarketPrice": info.get("regularMarketPrice"),
        }
        await redis.setex(cache_key, 3600, json.dumps(result))
        return result
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/history/{symbol}")
async def get_history(
    symbol: str,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    series = await _get_price_series(symbol, db, redis)
    if not series:
        raise HTTPException(status_code=404, detail=f"No data for {symbol}")
    df = _compute_analytics(series)
    return [
        {
            "date": str(r["date"])[:10],
            "open": None, "high": None, "low": None,
            "close": r["close"],
            "volume": None,
            "returns": None if pd.isna(r["returns"]) else float(r["returns"]),
            "ma20":    None if pd.isna(r["ma20"])    else float(r["ma20"]),
            "ma50":    None if pd.isna(r["ma50"])    else float(r["ma50"]),
        }
        for _, r in df.iterrows()
    ]


@router.get("/performance-heatmap/{symbol}")
async def get_heatmap(
    symbol: str,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    cache_key = f"heatmap:stock:{symbol.lower().replace('.', '_')}"
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)
    series = await _get_price_series(symbol, db, redis)
    if not series:
        raise HTTPException(status_code=404, detail=f"No data for {symbol}")
    df = _compute_analytics(series)
    df["year"]  = df["date"].dt.year
    df["month"] = df["date"].dt.month
    monthly = df.groupby(["year", "month"])["returns"].mean().reset_index()
    result = [
        {"year": int(r["year"]), "month": int(r["month"]), "value": round(float(r["returns"]), 6)}
        for _, r in monthly.iterrows()
        if not pd.isna(r["returns"])
    ]
    await redis.setex(cache_key, 1800, json.dumps(result))
    return result


@router.get("/risk-volatility/{symbol}")
async def get_risk(
    symbol: str,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    cache_key = f"risk:stock:{symbol.lower().replace('.', '_')}"
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)
    series = await _get_price_series(symbol, db, redis)
    if not series:
        raise HTTPException(status_code=404, detail=f"No data for {symbol}")
    df = _compute_analytics(series)
    result = _risk_metrics(df)
    await redis.setex(cache_key, 3600, json.dumps(result))
    return result


@router.get("/monte-carlo-prediction/{symbol}")
async def get_monte_carlo(
    symbol: str,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    cache_key = f"mc:stock:{symbol.lower().replace('.', '_')}"
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)
    series = await _get_price_series(symbol, db, redis)
    if not series:
        raise HTTPException(status_code=404, detail=f"No data for {symbol}")
    df = _compute_analytics(series)
    result = _monte_carlo(df)
    await redis.setex(cache_key, 21600, json.dumps(result))
    return result


@router.get("/news/{symbol}")
async def get_news(symbol: str, limit: int = 8, redis=Depends(get_redis)):
    cache_key = f"news:stock:{symbol.lower().replace('.', '_')}"
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)
    try:
        ticker = yf.Ticker(symbol)
        news = ticker.news or []
        items = [
            {
                "title": n.get("title", ""),
                "publisher": n.get("publisher", ""),
                "link": n.get("link", ""),
                "datetime": pd.to_datetime(n["providerPublishTime"], unit="s").strftime(
                    "%Y-%m-%d %H:%M:%S"
                ) if n.get("providerPublishTime") else "",
            }
            for n in news[:limit]
            if n.get("title")
        ]
        if items:
            await redis.setex(cache_key, 900, json.dumps(items))
        return items
    except Exception as e:
        return []
