from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from fastapi import Depends
from core.database import get_db
from core.redis import get_redis
from models.price_history import PriceHistory
from services.analytics import calc_risk_metrics, monte_carlo, numpy_to_python
import httpx, json, asyncio

router = APIRouter(prefix="/api/crypto", tags=["Crypto"])

COINGECKO = "https://api.coingecko.com/api/v3"


async def _get_price(symbol: str, redis) -> float | None:
    """Get crypto price from Binance Redis cache, fallback to CoinGecko API"""
    # Try Binance price from Redis first
    key = f"price:crypto:{symbol.lower()}usdt"
    val = await redis.get(key)
    if val:
        return float(val)

    # Fallback to CoinGecko
    try:
        # Map symbol to CoinGecko ID (e.g., btc -> bitcoin)
        coin_id_map = {
            "btc": "bitcoin", "eth": "ethereum", "sol": "solana",
            "bnb": "binancecoin", "ada": "cardano", "doge": "dogecoin",
            "xrp": "ripple", "trx": "tron", "avax": "avalanche-2"
        }
        coin_id = coin_id_map.get(symbol[:3].lower(), symbol.lower())

        cache_key = f"crypto:price:cg:{coin_id}"
        cached = await redis.get(cache_key)
        if cached:
            return float(cached)

        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{COINGECKO}/simple/price",
                params={"ids": coin_id, "vs_currencies": "usd"},
            )
        if r.status_code == 200:
            data = r.json()
            price = data.get(coin_id, {}).get("usd")
            if price:
                await redis.setex(cache_key, 300, str(price))  # 5min cache
                return float(price)
    except Exception as e:
        print(f"⚠️ CoinGecko fallback failed for {symbol}: {e}")

    return None


async def _get_price_series(symbol: str, db: AsyncSession) -> list[float]:
    result = await db.execute(
        select(PriceHistory.close_price)
        .where(PriceHistory.symbol == symbol)
        .order_by(desc(PriceHistory.price_date))
        .limit(365)
    )
    rows = result.scalars().all()
    return [float(r) for r in reversed(rows)]


@router.get("/famous")
async def get_famous_coins(redis=Depends(get_redis)):
    cache_key = "crypto:famous"
    cached = await redis.get(cache_key)
    if cached:
        data = json.loads(cached)
        # Always overlay fresh prices with fallback
        for coin in data:
            price = await _get_price(coin["symbol"], redis)
            if price:
                coin["current_price"] = price
        return data

    famous_ids = [
        "bitcoin", "ethereum", "solana", "binancecoin",
        "tether", "ripple", "cardano", "dogecoin", "tron", "avalanche-2"
    ]
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{COINGECKO}/coins/markets",
            params={
                "vs_currency": "usd",
                "ids": ",".join(famous_ids),
                "order": "market_cap_desc",
                "per_page": 10,
                "page": 1,
                "sparkline": "false",
            },
        )
    if not r.is_success:
        return []

    coins = []
    for c in r.json():
        coin = {
            "id": c["id"], "symbol": c["symbol"], "name": c["name"],
            "image": c.get("image"), "current_price": c.get("current_price"),
            "market_cap": c.get("market_cap"),
            "market_cap_rank": c.get("market_cap_rank"),
        }
        # Overlay fresh price with fallback
        price = await _get_price(c["symbol"], redis)
        if price:
            coin["current_price"] = price
        coins.append(coin)

    await redis.setex(cache_key, 300, json.dumps(coins))  # 5min cache
    return coins


@router.get("/coins")
async def get_coins(search: str = Query(default="")):
    redis = await get_redis()
    cache_key = f"crypto:search:{search.lower()}"
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    params = {
        "vs_currency": "usd", "order": "market_cap_desc",
        "per_page": 100, "page": 1, "sparkline": "false",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{COINGECKO}/coins/markets", params=params)
    if not r.is_success:
        return []

    results = r.json()
    if search:
        results = [
            c for c in results
            if search.lower() in (c.get("id","") + c.get("symbol","") + c.get("name","")).lower()
        ]

    coins = [
        {
            "id": c["id"], "symbol": c["symbol"], "name": c["name"],
            "image": c.get("image"), "current_price": c.get("current_price"),
            "market_cap": c.get("market_cap"),
            "market_cap_rank": c.get("market_cap_rank"),
        }
        for c in results[:50]
    ]
    await redis.setex(cache_key, 300, json.dumps(coins))
    return coins


@router.get("/coin-details/{coin_id}")
async def get_coin_details(coin_id: str, redis=Depends(get_redis)):
    cache_key = f"crypto:detail:{coin_id}"
    cached = await redis.get(cache_key)
    if cached:
        data = json.loads(cached)
        # Always overlay fresh price with fallback
        price = await _get_price(coin_id, redis)
        if price:
            data["current_price"] = price
        return data

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{COINGECKO}/coins/{coin_id}")
    if not r.is_success:
        raise HTTPException(status_code=404, detail="Coin not found")

    data = r.json()
    market = data.get("market_data", {})

    def safeget(d, *path):
        for p in path:
            if isinstance(d, dict): d = d.get(p)
            elif isinstance(d, list) and isinstance(p, int): d = d[p] if len(d) > p else None
            else: return None
        return d

    result = {
        "id": data.get("id"), "symbol": data.get("symbol"), "name": data.get("name"),
        "description": safeget(data, "description", "en") or "",
        "image": safeget(data, "image", "large"),
        "current_price": safeget(market, "current_price", "usd"),
        "market_cap": safeget(market, "market_cap", "usd"),
        "high_24h": safeget(market, "high_24h", "usd"),
        "low_24h": safeget(market, "low_24h", "usd"),
        "ath": safeget(market, "ath", "usd"),
        "price_change_percentage_24h": safeget(market, "price_change_percentage_24h_in_currency", "usd"),
        "circulating_supply": market.get("circulating_supply"),
    }
    # Overlay fresh price with fallback
    price = await _get_price(coin_id, redis)
    if price:
        result["current_price"] = price
    await redis.setex(cache_key, 300, json.dumps(result))
    return result


@router.get("/risk-volatility/{coin_id}")
async def get_risk_volatility(
    coin_id: str, db: AsyncSession = Depends(get_db)
):
    # Try DB price series first (from Binance worker)
    series = await _get_price_series(coin_id, db)

    # Fallback: CoinGecko historical
    if len(series) < 2:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{COINGECKO}/coins/{coin_id}/market_chart",
                params={"vs_currency": "usd", "days": 365},
            )
        if r.is_success:
            prices = r.json().get("prices", [])
            series = [p[1] for p in prices]

    if len(series) < 2:
        return {"annualized_volatility": 0.0, "annualized_return": 0.0, "sharpe_ratio": 0.0}

    risk = calc_risk_metrics(series)
    return {
        "annualized_volatility": risk["volatility"] / 100,
        "annualized_return": 0.0,
        "sharpe_ratio": risk["sharpe"],
        "max_drawdown": risk["max_drawdown"],
    }


@router.get("/monte-carlo-prediction/{coin_id}")
async def get_monte_carlo(coin_id: str, db: AsyncSession = Depends(get_db)):
    redis = await get_redis()
    cache_key = f"mc:crypto:{coin_id}"
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    series = await _get_price_series(coin_id, db)
    if len(series) < 10:
        raise HTTPException(status_code=404, detail="Insufficient data")

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


@router.get("/historical-price/{coin_id}")
async def get_historical_price(coin_id: str, db: AsyncSession = Depends(get_db)):
    # Try DB first
    result = await db.execute(
        select(PriceHistory)
        .where(PriceHistory.symbol == coin_id)
        .order_by(PriceHistory.price_date)
        .limit(365)
    )
    rows = result.scalars().all()
    if rows:
        return [{"date": str(r.price_date), "price": float(r.close_price)} for r in rows]

    # Fallback: CoinGecko
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{COINGECKO}/coins/{coin_id}/market_chart",
            params={"vs_currency": "usd", "days": 365},
        )
    if not r.is_success:
        return []
    return [
        {"date": str(p[0]), "price": p[1]}
        for p in r.json().get("prices", [])
    ]


@router.get("/performance-heatmap/{coin_id}")
async def get_performance_heatmap(coin_id: str, db: AsyncSession = Depends(get_db)):
    """Compute monthly price returns for a crypto asset."""
    # Try DB first
    result = await db.execute(
        select(PriceHistory)
        .where(PriceHistory.symbol == coin_id)
        .order_by(PriceHistory.price_date)
        .limit(365)
    )
    rows = result.scalars().all()

    from collections import defaultdict

    monthly: dict[tuple[int, int], list[float]] = defaultdict(list)

    if rows:
        for r in rows:
            d = r.price_date
            monthly[(d.year, d.month)].append(float(r.close_price))
    else:
        # Fallback: CoinGecko
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{COINGECKO}/coins/{coin_id}/market_chart",
                params={"vs_currency": "usd", "days": 365},
            )
        if resp.is_success:
            from datetime import datetime
            for ts, price in resp.json().get("prices", []):
                dt = datetime.fromtimestamp(ts / 1000)
                monthly[(dt.year, dt.month)].append(price)

    heatmap = []
    for (year, month), prices in sorted(monthly.items()):
        if len(prices) >= 2:
            ret = (prices[-1] - prices[0]) / prices[0]
            heatmap.append({"year": year, "month": month, "value": round(ret, 6)})

    return heatmap[-12:]
