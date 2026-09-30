def _aggregate_holdings_metrics(holdings: list) -> dict:
    """
    Compute aggregated metrics from holdings list.
    Returns dict with avg_xirr, avg_sharpe, avg_volatility, mc_p50_median
    """
    # Average XIRR across holdings
    xirr_values = [h.get("xirr", 0) for h in holdings if h.get("xirr")]
    avg_xirr = sum(xirr_values) / len(xirr_values) if xirr_values else 0.0

    # Average Sharpe from risk
    sharpe_values = [h.get("risk", {}).get("sharpe", 0) for h in holdings if h.get("risk")]
    avg_sharpe = sum(sharpe_values) / len(sharpe_values) if sharpe_values else 0.0

    # Average volatility from risk
    vol_values = [h.get("risk", {}).get("volatility", 0) for h in holdings if h.get("risk")]
    avg_volatility = sum(vol_values) / len(vol_values) if vol_values else 0.0

    # Median Monte Carlo p50 (expected 1yr value)
    mc_p50_values = [h.get("montecarlo", {}).get("p50", 0) for h in holdings if h.get("montecarlo")]
    mc_p50_median = sum(mc_p50_values) / len(mc_p50_values) if mc_p50_values else 0.0

    return {
        "avg_xirr": avg_xirr,
        "avg_sharpe": avg_sharpe,
        "avg_volatility": avg_volatility,
        "mc_p50_median": mc_p50_median,
    }


def build_dost_prompt(portfolio_summary: dict) -> tuple[str, str]:
    system = """You are AI Dost, a friendly Indian personal finance assistant.
You speak in a warm, clear tone — like a knowledgeable friend, not a banker.
Give practical, actionable advice. Use INR where relevant. Be concise (max 200 words)."""

    # Extract direct keys from summary
    total_invested = float(portfolio_summary.get("total_invested", 0) or 0)
    total_current = float(portfolio_summary.get("total_current_value", 0) or 0)
    total_pnl = float(portfolio_summary.get("total_pnl", 0) or 0)
    total_pnl_pct = float(portfolio_summary.get("total_pnl_pct", 0) or 0)

    # Get portfolio-level risk metrics (computed from enriched summary)
    sharpe_ratio = float(portfolio_summary.get("sharpe_ratio", 0) or 0)
    volatility = float(portfolio_summary.get("volatility", 0) or 0)
    max_drawdown = float(portfolio_summary.get("max_drawdown", 0) or 0)
    monte_carlo_median = float(portfolio_summary.get("monte_carlo_median", 0) or 0)

    # Get enriched holdings
    holdings = portfolio_summary.get("holdings", [])
    holdings_count = len(holdings)
    asset_types = portfolio_summary.get("asset_types", [])

    # Determine portfolio state
    has_basic_metrics = total_invested > 0 and total_current > 0

    # Build overall metrics section
    overall_section = f"""**Overall Portfolio:**
- Total Invested: ₹{total_invested:,.0f}
- Current Value: ₹{total_current:,.0f}
- Total P&L: ₹{total_pnl:,.0f} ({total_pnl_pct:.1f}%)
- XIRR: {float(portfolio_summary.get('xirr', 0) or 0):.1f}%
- Sharpe Ratio: {sharpe_ratio:.2f}
- Volatility: {volatility:.1f}%
- Max Drawdown: {max_drawdown:.1f}%
- Monte Carlo median 1yr value: ₹{monte_carlo_median:,.0f}
- Holdings: {holdings_count} assets across {', '.join(asset_types) if asset_types else 'various types'}"""

    # Build top holdings section if holdings exist
    top_holdings_section = ""
    if holdings:
        top_holdings = holdings[:5]  # Top 5 by allocation
        holdings_lines = []
        for h in top_holdings:
            symbol = h.get("symbol", "N/A")
            name = h.get("name", symbol)
            allocation = float(h.get("allocation_pct", 0) or 0)
            pnl_pct = float(h.get("pnl_pct", 0) or 0)
            xirr = float(h.get("xirr", 0) or 0)
            sharpe = float(h.get("sharpe", 0) or 0)
            risk_vol = float(h.get("volatility", 0) or 0)
            holdings_lines.append(
                f"- {name} ({symbol}): {allocation:.1f}% allocation, {pnl_pct:.1f}% P&L, {xirr:.1f}% XIRR, Sharpe {sharpe:.2f}, Volatility {risk_vol:.1f}%"
            )
        top_holdings_text = "\n".join(holdings_lines)
        top_holdings_section = f"\n\n**Top Holdings (by allocation):**\n{top_holdings_text}"

    # Add note if risk metrics are zero but portfolio is real
    risk_note = ""
    if has_basic_metrics and (sharpe_ratio == 0 or volatility == 0 or max_drawdown == 0):
        risk_note = "\n\nNote: Some advanced metrics are 0.0 right now, which usually means there isn't enough historical price data yet, not a problem with your portfolio."

    user = f"""{overall_section}{top_holdings_section}{risk_note}

Give a brief, friendly analysis of the overall portfolio and comment on the most important holdings (top 3-5 by allocation or risk). Then give 2-3 actionable suggestions."""

    return system, user


def build_report_prompt(portfolio_summary: dict) -> tuple[str, str]:
    system = """You are a professional financial analyst. Generate a structured portfolio report.
Use markdown formatting with headers. Be data-driven and objective. Max 400 words."""

    # Extract direct keys from summary
    total_invested = float(portfolio_summary.get("total_invested", 0) or 0)
    total_current = float(portfolio_summary.get("total_current_value", 0) or 0)
    total_pnl = float(portfolio_summary.get("total_pnl", 0) or 0)
    total_pnl_pct = float(portfolio_summary.get("total_pnl_pct", 0) or 0)

    # Get portfolio-level risk metrics (computed from enriched summary)
    sharpe_ratio = float(portfolio_summary.get("sharpe_ratio", 0) or 0)
    volatility = float(portfolio_summary.get("volatility", 0) or 0)
    max_drawdown = float(portfolio_summary.get("max_drawdown", 0) or 0)
    monte_carlo_median = float(portfolio_summary.get("monte_carlo_median", 0) or 0)

    # Get enriched holdings
    holdings = portfolio_summary.get("holdings", [])
    asset_types = portfolio_summary.get("asset_types", [])

    # Determine portfolio state
    has_real_investment = total_invested > 0
    has_limited_data = (sharpe_ratio == 0 or volatility == 0 or max_drawdown == 0 or monte_carlo_median == 0)

    # Build comprehensive holdings breakdown
    holdings_lines = []
    for h in holdings:
        symbol = h.get("symbol", "N/A")
        name = h.get("name", symbol)
        assettype = h.get("assettype", "unknown")
        allocation = float(h.get("allocation_pct", 0) or 0)
        pnl_pct = float(h.get("pnl_pct", 0) or 0)
        pnl_abs = float(h.get("pnl_abs", 0) or 0)
        xirr = float(h.get("xirr", 0) or 0)
        sharpe = float(h.get("sharpe", 0) or 0)
        risk_vol = float(h.get("volatility", 0) or 0)
        mdd = float(h.get("max_drawdown", 0) or 0)
        mc_p50 = float(h.get("monte_carlo_p50", 0) or 0)

        holdings_lines.append(
            f"- **{name}** ({symbol}, {assettype}): {allocation:.1f}% allocation, {pnl_pct:.1f}% P&L (₹{pnl_abs:,.0f}), XIRR {xirr:.1f}%, Sharpe {sharpe:.2f}, Volatility {risk_vol:.1f}%, Max DD {mdd:.1f}%, MC median ₹{mc_p50:,.0f}"
        )
    holdings_text = "\n".join(holdings_lines) if holdings_lines else "(No holdings data)"

    # Build conditional text blocks
    portfolio_status = ""
    if has_real_investment:
        portfolio_status = f"Initial investment of ₹{total_invested:,.0f} with current value ₹{total_current:,.0f}, representing a total P&L of ₹{total_pnl:,.0f} ({total_pnl_pct:.1f}%)."
    else:
        portfolio_status = "No active investments or entirely in cash."

    risk_note = ""
    if has_limited_data:
        risk_note = "\n\n**Data Note:** Some predictive and risk metrics are 0.0, usually due to insufficient historical price data. This does not indicate a portfolio problem."

    user = f"""Generate a detailed portfolio health report with these metrics:

**Overall Summary**
- Total Invested: ₹{total_invested:,.0f}
- Current Value: ₹{total_current:,.0f}
- Total P&L: ₹{total_pnl:,.0f} ({total_pnl_pct:.1f}%)
- Portfolio XIRR: {float(portfolio_summary.get('xirr', 0) or 0):.1f}%
- Sharpe Ratio: {sharpe_ratio:.2f}
- Volatility: {volatility:.1f}%
- Max Drawdown: {max_drawdown:.1f}%
- Monte Carlo 1yr Median: ₹{monte_carlo_median:,.0f}
- Asset types: {', '.join(asset_types) if asset_types else 'various'}

**Portfolio Status:** {portfolio_status}

**Holdings Breakdown** (with allocation %, P&L %, XIRR, Sharpe, volatility, max drawdown, Monte Carlo median):
{holdings_text}{risk_note}

Write a markdown report with sections:
1. **Executive Summary** — Overall investment status and performance
2. **Allocation & Diversification** — Asset distribution and diversification analysis
3. **Risk Assessment** — Discuss volatility, Sharpe ratio, max drawdown, and diversification benefits
4. **Performance by Asset** — Mention specific stocks, mutual funds, and cryptos with their individual P&L and XIRR
5. **Growth Outlook & Recommendations** — Discuss Monte Carlo insights and provide 2-3 actionable suggestions"""

    return system, user
