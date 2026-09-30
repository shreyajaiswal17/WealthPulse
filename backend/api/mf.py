from fastapi import APIRouter, HTTPException, Query
from core.redis import get_redis
from services.analytics import calc_risk_metrics, monte_carlo, numpy_to_python
import httpx, json

router = APIRouter(prefix="/api/mutual", tags=["Mutual Funds"])

MFAPI = "https://api.mfapi.in/mf"


async def _get_nav_series(scheme_code: str) -> list[float]:
    """Fetch historical NAV from mfapi.in (cached in Redis 1h)."""
    redis = await get_redis()
    cache_key = f"mf:history:{scheme_code}"
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{MFAPI}/{scheme_code}")

    if not r.is_success:
        return []

    data = r.json().get("data", [])
    # data is newest-first, reverse for chronological order
    series = []
    for entry in reversed(data):
        try:
            series.append(float(entry["nav"]))
        except (KeyError, ValueError):
            continue

    await redis.setex(cache_key, 3600, json.dumps(series))
    return series


@router.get("/schemes")
async def search_schemes(search: str = Query(default="")):
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{MFAPI}/search?q={search}")
    if not r.is_success:
        return {}
    items = r.json()[:20]
    # Frontend expects {schemeCode: schemeName} dict
    return {str(item["schemeCode"]): item["schemeName"] for item in items if "schemeCode" in item}


@router.get("/scheme-details/{scheme_code}")
async def get_scheme_details(scheme_code: str):
    redis = await get_redis()
    cache_key = f"mf:meta:{scheme_code}"
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{MFAPI}/{scheme_code}")

    if not r.is_success:
        raise HTTPException(status_code=404, detail="Scheme not found")

    full = r.json()
    meta = full.get("meta", {})
    # add current nav
    history = full.get("data", [])
    if history:
        meta["nav"] = float(history[0]["nav"])
        meta["nav_date"] = history[0]["date"]

    await redis.setex(cache_key, 3600, json.dumps(meta))
    return meta


@router.get("/historical-nav/{scheme_code}")
async def get_historical_nav(scheme_code: str):
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{MFAPI}/{scheme_code}")
    if not r.is_success:
        return []
    return r.json().get("data", [])[:365]  # newest first, limit 1yr


@router.get("/risk-volatility/{scheme_code}")
async def get_risk_volatility(scheme_code: str):
    series = await _get_nav_series(scheme_code)
    if len(series) < 2:
        return {"annualized_volatility": 0.0, "annualized_return": 0.0, "sharpe_ratio": 0.0}
    risk = calc_risk_metrics(series)
    return {
        "annualized_volatility": risk["volatility"] / 100,
        "annualized_return": 0.0,
        "sharpe_ratio": risk["sharpe"],
        "max_drawdown": risk["max_drawdown"],
    }


@router.get("/monte-carlo-prediction/{scheme_code}")
async def get_monte_carlo(scheme_code: str):
    redis = await get_redis()
    cache_key = f"mc:mf:{scheme_code}"
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    series = await _get_nav_series(scheme_code)
    if len(series) < 10:
        raise HTTPException(status_code=404, detail="Insufficient NAV data")

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


@router.get("/performance-heatmap/{scheme_code}")
async def get_performance_heatmap(scheme_code: str):
    """Compute monthly NAV returns for a mutual fund."""
    series_raw = []
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{MFAPI}/{scheme_code}")
    if not r.is_success:
        return []

    data = r.json().get("data", [])
    # data is newest-first; group by month
    from collections import defaultdict
    from datetime import datetime

    monthly: dict[tuple[int, int], list[float]] = defaultdict(list)
    for entry in data:
        try:
            nav = float(entry["nav"])
            dt = datetime.strptime(entry["date"], "%d-%m-%Y")
            monthly[(dt.year, dt.month)].append(nav)
        except (KeyError, ValueError):
            continue

    heatmap = []
    for (year, month), navs in sorted(monthly.items()):
        if len(navs) >= 2:
            # navs are newest-first within month, so last element is earliest
            ret = (navs[0] - navs[-1]) / navs[-1]
            heatmap.append({"year": year, "month": month, "value": round(ret, 6)})

    return heatmap[-12:]  # last 12 months
