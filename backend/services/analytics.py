import numpy as np
import pandas as pd
from scipy.optimize import brentq
from datetime import date, datetime
from typing import List, Dict, Any


# ── P&L ────────────────────────────────────────────────────────────────────

def calc_pnl(buy_price: float, current_price: float, quantity: float) -> Dict:
    invested = buy_price * quantity
    current_value = current_price * quantity
    pnl = current_value - invested
    pnl_pct = (pnl / invested) * 100 if invested else 0
    return {
        "invested": round(invested, 2),
        "current_value": round(current_value, 2),
        "pnl": round(pnl, 2),
        "pnl_pct": round(pnl_pct, 2),
    }


# ── XIRR ───────────────────────────────────────────────────────────────────

def xirr(cashflows: List[tuple]) -> float | None:
    """
    Calculate annualized IRR from cashflows.

    Args:
        cashflows: List of (date, amount) tuples.
                   Negative = outflow (buy), Positive = inflow (current value).

    Returns:
        Annualized IRR as a percentage (e.g., 14.5 for 14.5%), rounded to 2 decimals.
        Returns None if:
        - Less than 2 cashflows
        - Holding age < 30 days (insufficient history)
        - Solver fails or no valid IRR exists
    """
    if len(cashflows) < 2:
        return None

    dates = [cf[0] for cf in cashflows]
    amounts = [cf[1] for cf in cashflows]
    t0 = dates[0]
    days = [(d - t0).days for d in dates]

    # If holding is too new (< 30 days old), XIRR is unreliable
    max_age_days = max(days)
    if max_age_days < 30:
        return None

    def npv(rate):
        return sum(a / (1 + rate) ** (d / 365.0) for a, d in zip(amounts, days))

    try:
        return round(brentq(npv, -0.999, 100.0, maxiter=100) * 100, 2)
    except Exception:
        return None


# ── RISK METRICS ───────────────────────────────────────────────────────────

def calc_risk_metrics(price_series: List[float]) -> Dict:
    if len(price_series) < 2:
        return {"volatility": 0, "sharpe": 0, "max_drawdown": 0}

    prices = np.array(price_series)
    returns = np.diff(prices) / prices[:-1]

    volatility = round(float(np.std(returns) * np.sqrt(252)) * 100, 2)

    mean_return = np.mean(returns) * 252
    std_return = np.std(returns) * np.sqrt(252)
    risk_free = 0.065  # 6.5% Indian risk-free rate
    sharpe = round(float((mean_return - risk_free) / std_return), 2) if std_return else 0

    peak = np.maximum.accumulate(prices)
    drawdown = (prices - peak) / peak
    max_drawdown = round(float(np.min(drawdown)) * 100, 2)

    return numpy_to_python({
        "volatility": volatility,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
    })


# ── MONTE CARLO ────────────────────────────────────────────────────────────

def monte_carlo(
    current_value: float,
    price_series: List[float],
    days: int = 365,
    simulations: int = 500,
) -> Dict:
    if len(price_series) < 2:
        return {"p10": 0, "p50": 0, "p90": 0}

    prices = np.array(price_series)
    returns = np.diff(prices) / prices[:-1]

    # guard: if returns are all zero or nan, skip simulation
    if np.all(returns == 0) or np.any(np.isnan(returns)) or np.std(returns) == 0:
        return {"p10": current_value, "p50": current_value, "p90": current_value, "current_value": round(current_value, 2)}

    mu = np.mean(returns)
    sigma = np.std(returns)

    results = []
    for _ in range(simulations):
        daily = np.random.normal(mu, sigma, days)
        final = current_value * np.prod(1 + daily)
        results.append(final)

    results = sorted(results)
    n = len(results)
    return numpy_to_python({
        "p10": round(results[int(n * 0.10)], 2),
        "p50": round(results[int(n * 0.50)], 2),
        "p90": round(results[int(n * 0.90)], 2),
        "current_value": round(current_value, 2),
    })


# ── SERIALIZATION FIX ──────────────────────────────────────────────────────

def numpy_to_python(obj):
    """Convert numpy types to native Python for JSON serialization."""
    if isinstance(obj, dict):
        return {k: numpy_to_python(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [numpy_to_python(v) for v in obj]
    if isinstance(obj, float):
        if obj != obj or obj == float('inf') or obj == float('-inf'):
            return 0  # replace nan/inf with 0
        return obj
    if isinstance(obj, (np.float32, np.float64)):
        v = float(obj)
        if v != v or v == float('inf') or v == float('-inf'):
            return 0
        return v
    if isinstance(obj, (np.int32, np.int64)):
        return int(obj)
    return obj

