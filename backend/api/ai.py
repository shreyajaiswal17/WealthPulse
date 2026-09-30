from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from core.security import get_current_user
from services.ai import call_ai
from services.prompt_builder import build_dost_prompt, build_report_prompt
from api.analytics import portfolio_analytics
from core.limiter import limiter

router = APIRouter(prefix="/api/ai", tags=["AI"])


def build_portfolio_summary_for_ai(analytics: dict) -> dict:
    """
    Build a rich summary object suitable for AI prompt builders.
    Includes overall metrics and enriched per-holding data with full analytics.
    """
    summary = dict(analytics.get("summary", {}))  # copy overall summary
    holdings = analytics.get("holdings", [])

    # Add holdings count and asset types
    summary["holdings_count"] = len(holdings)
    summary["asset_types"] = sorted({h.get("asset_type", "") for h in holdings if h.get("asset_type")})

    # Compute portfolio-level risk aggregates (median/average of per-holding values)
    sharpe_values = [h.get("risk", {}).get("sharpe") for h in holdings if h.get("risk", {}).get("sharpe") is not None]
    vol_values = [h.get("risk", {}).get("volatility") for h in holdings if h.get("risk", {}).get("volatility") is not None]
    mdd_values = [h.get("risk", {}).get("maxdrawdown") for h in holdings if h.get("risk", {}).get("maxdrawdown") is not None]
    mc_medians = [h.get("montecarlo", {}).get("p50") for h in holdings if h.get("montecarlo", {}).get("p50") is not None]

    def _safe_median(values):
        """Calculate median safely from a list of values."""
        v = [float(x) for x in values if x is not None]
        if not v:
            return 0.0
        v = sorted(v)
        n = len(v)
        if n % 2 == 1:
            return v[n // 2]
        return (v[n // 2 - 1] + v[n // 2]) / 2.0

    summary["sharpe_ratio"] = _safe_median(sharpe_values)
    summary["volatility"] = _safe_median(vol_values)
    summary["max_drawdown"] = _safe_median(mdd_values)
    summary["monte_carlo_median"] = _safe_median(mc_medians)

    # Build enriched holdings list
    enriched_holdings = []
    total_invested = summary.get("total_invested", 0) or 0

    for h in holdings:
        risk = h.get("risk", {}) or {}
        mc = h.get("montecarlo", {}) or {}
        # Note: pnl fields are spread directly into the holding object from analytics
        invested = float(h.get("invested", 0) or 0)
        current_value = float(h.get("current_value", 0) or 0)
        pnl_abs = float(h.get("pnl", 0) or 0)
        pnl_pct = float(h.get("pnl_pct", 0) or 0)

        allocation_pct = (invested / total_invested * 100) if total_invested else 0.0

        enriched_holdings.append({
            "symbol": h.get("symbol", "N/A"),
            "name": h.get("name", "Unknown"),
            "assettype": h.get("asset_type", "unknown"),
            "allocation_pct": round(allocation_pct, 2),
            "pnl_pct": round(pnl_pct, 2),
            "pnl_abs": round(pnl_abs, 2),
            "xirr": float(h.get("xirr") or 0.0),
            "volatility": float(risk.get("volatility") or 0.0),
            "sharpe": float(risk.get("sharpe") or 0.0),
            "max_drawdown": float(risk.get("maxdrawdown") or 0.0),
            "monte_carlo_p50": float(mc.get("p50") or 0.0),
            "monte_carlo_p10": float(mc.get("p10") or 0.0),
            "monte_carlo_p90": float(mc.get("p90") or 0.0),
        })

    # Sort holdings by allocation (descending)
    enriched_holdings.sort(key=lambda x: x.get("allocation_pct", 0), reverse=True)

    summary["holdings"] = enriched_holdings
    return summary


@router.get("/dost")
@limiter.limit("10/minute")
async def ai_dost(
    request: Request,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    analytics = await portfolio_analytics(user=user, db=db)
    portfolio_summary = build_portfolio_summary_for_ai(analytics)
    system, user_prompt = build_dost_prompt(portfolio_summary)
    reply = await call_ai(system, user_prompt)
    return {"text": reply, "format": "markdown"}


@router.get("/report")
@limiter.limit("5/minute")
async def ai_report(
    request: Request,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    analytics = await portfolio_analytics(user=user, db=db)
    portfolio_summary = build_portfolio_summary_for_ai(analytics)
    system, user_prompt = build_report_prompt(portfolio_summary)
    reply = await call_ai(system, user_prompt)
    return {"text": reply, "format": "markdown"}
