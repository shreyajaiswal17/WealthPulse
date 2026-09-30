import json
import httpx
import asyncio
import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.database import get_db
from core.redis import get_redis
from models.price_history import PriceHistory
from services.price_backfill import ensure_crypto_history, COIN_ID_TO_SYMBOL

router = APIRouter(prefix="/api/crypto", tags=["Crypto Compat"])
COINGECKO_BASE = "https://api.coingecko.com/api/v3"
FAMOUS_IDS = ["bitcoin", "ethereum", "solana", "binancecoin",
              "cardano", "dogecoin", "ripple", "tron", "avalanche-2", "polkadot"]


async def _get_crypto_price(coin_id: str, redis) -> float | None:
    """
    Fetch crypto price with Binance → CoinGecko fallback.
    First tries Binance price from Redis, then queries CoinGecko API.
    """
    # Try Binance price from Redis (populated by binance_ws.py)
    binance_sym = COIN_ID_TO_SYMBOL.get(coin_id)
    if binance_sym:
        live = await redis.get(f"price:crypto:{binance_sym}")
        if live:
            return float(live)

    # Fallback to CoinGecko
    try:
        cache_key = f"crypto:price:{coin_id}"
        cached = await redis.get(cache_key)
        if cached:
            return float(cached)

        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{COINGECKO_BASE}/simple/price",
                params={"ids": coin_id, "vs_currencies": "usd"},
            )
        if r.status_code == 200:
            data = r.json()
            price = data.get(coin_id, {}).get("usd")
            if price:
                await redis.setex(cache_key, 300, str(price))  # 5min cache
                return float(price)
    except Exception as e:
        print(f"⚠️ CoinGecko fallback failed for {coin_id}: {e}")

    return None


async def _get_price_series(coin_id: str, db: AsyncSession, redis) -> list[dict]:
    symbol = COIN_ID_TO_SYMBOL.get(coin_id)
    if not symbol:
        return []

    cache_key = f"pseries:crypto:{coin_id}"
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    result = await db.execute(
        select(PriceHistory)
        .where(PriceHistory.symbol == symbol, PriceHistory.asset_type == "crypto")
        .order_by(PriceHistory.price_date)
        .limit(365)
    )
    rows = result.scalars().all()

    if len(rows) < 30:
        await ensure_crypto_history(coin_id, db)
        result = await db.execute(
            select(PriceHistory)
            .where(PriceHistory.symbol == symbol, PriceHistory.asset_type == "crypto")
            .order_by(PriceHistory.price_date)
            .limit(365)
        )
        rows = result.scalars().all()

    series = [{"date": str(r.price_date), "price": float(r.close_price)} for r in rows]
    if series:
        await redis.setex(cache_key, 1800, json.dumps(series))
    return series


def _price_df(series: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(series)
    df["date"] = pd.to_datetime(df["date"])
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df.dropna(subset=["price"], inplace=True)
    df["returns"] = df["price"].pct_change()
    return df


def _risk_metrics(df: pd.DataFrame) -> dict:
    returns = df["returns"].dropna()
    ann_vol = float(returns.std() * (252 ** 0.5))
    ann_ret = float((returns.mean() + 1) ** 252 - 1)
    sharpe = float((ann_ret - 0.06) / ann_vol) if ann_vol > 0 else 0.0
    return {
        "annualized_volatility": ann_vol,
        "annualized_return": ann_ret,
        "sharpe_ratio": sharpe,
        "returns": [
            {"date": str(r["date"])[:10], "returns": round(float(r["returns"]), 8)}
            for _, r in df.iterrows() if not pd.isna(r["returns"])
        ],
    }


def _monte_carlo(df: pd.DataFrame) -> dict:
    returns = df["returns"].dropna()
    if len(returns) < 10:
        return {"message": "Insufficient data"}
    mu, sigma = float(returns.mean()), float(returns.std())
    last_price = float(df["price"].iloc[-1])
    num_simulations, days = 1000, 252
    sims = np.zeros((num_simulations, days))
    sims[:, 0] = last_price
    for t in range(1, days):
        sims[:, t] = sims[:, t - 1] * (1 + np.random.normal(mu, sigma, num_simulations))

    # Generate simulation paths (4 sample paths)
    sim_paths = [
        {"name": f"Simulation {i + 1}",
         "data": [{"day": d, "value": float(sims[i, d])} for d in range(0, days, 5)]}
        for i in range(4)
    ]

    # Generate historical predicted (mean of all simulations)
    historical_predicted = [
        {"day": d, "value": float(np.mean(sims[:, d]))} for d in range(0, days, 5)
    ]

    return {
        "expected_price": float(np.mean(sims[:, -1])),
        "probability_positive_return": float(np.mean(sims[:, -1] > last_price) * 100),
        "lower_bound_5th_percentile": float(np.percentile(sims[:, -1], 5)),
        "upper_bound_95th_percentile": float(np.percentile(sims[:, -1], 95)),
        "last_price": last_price,
        "simulation_paths": sim_paths,
        "historical_predicted": historical_predicted,
    }


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/coins")
async def get_coins(search: str = "", redis=Depends(get_redis)):
    cache_key = f"cg:coins:{search.lower()[:30]}"
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{COINGECKO_BASE}/coins/markets",
            params={"vs_currency": "usd", "order": "market_cap_desc",
                    "per_page": 100, "page": 1, "sparkline": "false"},
            timeout=15,
        )
    if r.status_code != 200:
        return []
    coins = r.json()
    if search:
        q = search.lower()
        coins = [c for c in coins if q in (c.get("id","") + c.get("symbol","") + c.get("name","")).lower()]
    result = [
        {"id": c["id"], "symbol": c["symbol"], "name": c["name"],
         "image": c.get("image"), "current_price": c.get("current_price"),
         "market_cap": c.get("market_cap"), "market_cap_rank": c.get("market_cap_rank")}
        for c in coins[:100]
    ]
    await redis.setex(cache_key, 3600, json.dumps(result))
    return result


@router.get("/famous")
async def get_famous(redis=Depends(get_redis)):
    cache_key = "cg:famous"
    cached = await redis.get(cache_key)
    if cached:
        data = json.loads(cached)
        # Always overlay fresh prices (Binance → CoinGecko fallback)
        for item in data:
            price = await _get_crypto_price(item["id"], redis)
            if price:
                item["current_price"] = price
        return data

    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{COINGECKO_BASE}/coins/markets",
            params={"vs_currency": "usd", "ids": ",".join(FAMOUS_IDS),
                    "order": "market_cap_desc", "per_page": 10,
                    "page": 1, "sparkline": "false"},
            timeout=15,
        )
    if r.status_code != 200:
        return []
    result = []
    for c in r.json():
        price = await _get_crypto_price(c["id"], redis)
        result.append({
            "id": c["id"], "symbol": c["symbol"], "name": c["name"],
            "image": c.get("image"),
            "current_price": price if price else c.get("current_price"),
            "market_cap": c.get("market_cap"),
            "market_cap_rank": c.get("market_cap_rank"),
        })
    await redis.setex(cache_key, 3600, json.dumps(result))  # cache metadata, price overlaid fresh
    return result


@router.get("/coin-details/{coin_id}")
async def get_coin_details(coin_id: str, redis=Depends(get_redis)):
    cache_key = f"cg:detail:{coin_id}"
    cached = await redis.get(cache_key)
    if cached:
        data = json.loads(cached)
        price = await _get_crypto_price(coin_id, redis)
        if price:
            data["current_price"] = price
        return data

    async with httpx.AsyncClient() as client:
        r = await client.get(f"{COINGECKO_BASE}/coins/{coin_id}", timeout=15)
    if not r.is_success:
        raise HTTPException(status_code=404, detail="Coin not found")
    raw = r.json()
    market = raw.get("market_data", {})

    def _get(d, *path):
        for p in path:
            if isinstance(d, dict):
                d = d.get(p)
            elif isinstance(d, list) and isinstance(p, int) and len(d) > p:
                d = d[p]
            else:
                return None
            if d is None:
                return None
        return d

    result = {
        "id": raw.get("id"),
        "symbol": raw.get("symbol"),
        "name": raw.get("name"),
        "description": _get(raw, "description", "en") or "",
        "image": _get(raw, "image", "large"),
        "current_price": _get(market, "current_price", "usd"),
        "market_cap": _get(market, "market_cap", "usd"),
        "total_volume": _get(market, "total_volume", "usd"),
        "ath": _get(market, "ath", "usd"),
        "atl": _get(market, "atl", "usd"),
        "high_24h": _get(market, "high_24h", "usd"),
        "low_24h": _get(market, "low_24h", "usd"),
        "price_change_percentage_24h": _get(market, "price_change_percentage_24h_in_currency", "usd"),
        "price_change_percentage_1y": _get(market, "price_change_percentage_1y_in_currency", "usd"),
        "circulating_supply": market.get("circulating_supply"),
    }
    price = await _get_crypto_price(coin_id, redis)
    if price:
        result["current_price"] = price
    await redis.setex(cache_key, 3600, json.dumps(result))
    return result


@router.get("/historical-price/{coin_id}")
async def get_historical_price(
    coin_id: str,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    series = await _get_price_series(coin_id, db, redis)
    if not series:
        raise HTTPException(status_code=404, detail=f"No data for {coin_id}")
    return series


@router.get("/performance-heatmap/{coin_id}")
async def get_heatmap(
    coin_id: str,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    cache_key = f"cg:heatmap:{coin_id}"
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)
    series = await _get_price_series(coin_id, db, redis)
    if not series:
        raise HTTPException(status_code=404, detail=f"No data for {coin_id}")
    df = _price_df(series)
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    monthly = df.groupby(["year", "month"])["returns"].mean().reset_index()
    result = [
        {"year": int(r["year"]), "month": int(r["month"]), "value": round(float(r["returns"]), 6)}
        for _, r in monthly.iterrows() if not pd.isna(r["returns"])
    ]
    await redis.setex(cache_key, 1800, json.dumps(result))
    return result


@router.get("/risk-volatility/{coin_id}")
async def get_risk(
    coin_id: str,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    cache_key = f"cg:risk:{coin_id}"
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)
    series = await _get_price_series(coin_id, db, redis)
    if not series:
        raise HTTPException(status_code=404, detail=f"No data for {coin_id}")
    result = _risk_metrics(_price_df(series))
    await redis.setex(cache_key, 3600, json.dumps(result))
    return result


@router.get("/monte-carlo-prediction/{coin_id}")
async def get_monte_carlo(
    coin_id: str,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    cache_key = f"cg:mc:{coin_id}"
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)
    series = await _get_price_series(coin_id, db, redis)
    if not series:
        raise HTTPException(status_code=404, detail=f"No data for {coin_id}")
    result = _monte_carlo(_price_df(series))
    await redis.setex(cache_key, 21600, json.dumps(result))
    return result


@router.get("/compare-prices")
async def compare_prices(
    coin_ids: str = Query(..., description="Comma-separated coin IDs e.g. bitcoin,ethereum"),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    ids = [c.strip() for c in coin_ids.split(",")]
    comparison = {}
    for coin_id in ids:
        series = await _get_price_series(coin_id, db, redis)
        if series:
            df = pd.DataFrame(series).set_index("date")["price"]
            comparison[coin_id] = df
    if not comparison:
        return []
    combined = pd.concat(comparison.values(), axis=1, keys=comparison.keys()).reset_index()
    combined.columns = ["date"] + [f"{cid}_price" for cid in comparison.keys()]
    return combined.fillna("").astype(str).to_dict(orient="records")
