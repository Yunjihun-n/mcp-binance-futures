"""Account tools: balance, positions, summary, income."""

from ..server import mcp, get_client, mode_prefix
from ..safety import audit_log
from ..server import AUDIT_DIR, get_mode


@mcp.tool()
async def check_balance(asset: str = "") -> str:
    """
    선물 지갑 잔고를 확인합니다.

    특정 자산만 보려면 asset에 'USDT', 'USDC' 등을 입력하세요.
    비워두면 잔고가 있는 모든 자산을 보여줍니다.
    """
    client = get_client()
    balances = await client.get_balance()

    if asset:
        balances = [b for b in balances if b.get("asset", "").upper() == asset.upper()]

    # Filter to non-zero balances
    active = [b for b in balances if float(b.get("balance", 0)) != 0 or float(b.get("crossUnPnl", 0)) != 0]

    if not active:
        return f"{mode_prefix()}잔고가 없습니다." + (f" (자산: {asset})" if asset else "")

    lines = [f"{mode_prefix()}💰 선물 지갑 잔고\n"]
    for b in active:
        bal = float(b.get("balance", 0))
        avail = float(b.get("availableBalance", 0))
        pnl = float(b.get("crossUnPnl", 0))
        lines.append(
            f"  {b['asset']}: 잔고 {bal:,.4f} | 사용가능 {avail:,.4f} | 미실현PnL {pnl:+,.4f}"
        )

    audit_log("check_balance", {"asset": asset}, get_mode(), "ok", AUDIT_DIR)
    return "\n".join(lines)


@mcp.tool()
async def view_positions(symbol: str = "") -> str:
    """
    열린 포지션을 확인합니다.

    진입가, 수량, 미실현PnL, 청산가 등을 보여줍니다.
    symbol을 지정하면 해당 심볼만 보여줍니다 (예: BTCUSDT).
    """
    client = get_client()
    positions = await client.get_position_risk(symbol or None)

    # Filter to non-zero positions
    active = [p for p in positions if float(p.get("positionAmt", 0)) != 0]

    if not active:
        return f"{mode_prefix()}열린 포지션이 없습니다." + (f" (심볼: {symbol})" if symbol else "")

    lines = [f"{mode_prefix()}📊 열린 포지션\n"]
    for p in active:
        amt = float(p.get("positionAmt", 0))
        entry = float(p.get("entryPrice", 0))
        mark = float(p.get("markPrice", 0))
        pnl = float(p.get("unRealizedProfit", 0))
        liq = p.get("liquidationPrice", "N/A")
        lev = p.get("leverage", "?")
        side = "LONG" if amt > 0 else "SHORT"
        lines.append(
            f"  {p['symbol']} {side} | 수량: {abs(amt)} | 진입가: {entry:,.2f} | "
            f"현재가: {mark:,.2f} | PnL: {pnl:+,.4f} | 청산가: {liq} | 레버리지: {lev}x"
        )

    audit_log("view_positions", {"symbol": symbol}, get_mode(), "ok", AUDIT_DIR)
    return "\n".join(lines)


@mcp.tool()
async def account_summary() -> str:
    """
    계좌 전체 요약을 한눈에 보여줍니다.

    총 잔고, 사용 가능 잔고, 마진 비율, 미실현PnL, 열린 포지션 수를 포함합니다.
    """
    client = get_client()
    account = await client.get_account()

    total_balance = float(account.get("totalWalletBalance", 0))
    available = float(account.get("availableBalance", 0))
    unrealized = float(account.get("totalUnrealizedProfit", 0))
    margin_used = float(account.get("totalInitialMargin", 0))
    maint_margin = float(account.get("totalMaintMargin", 0))

    positions = account.get("positions", [])
    active_positions = [p for p in positions if float(p.get("positionAmt", 0)) != 0]

    margin_ratio = (maint_margin / total_balance * 100) if total_balance > 0 else 0

    lines = [
        f"{mode_prefix()}📋 계좌 요약",
        f"",
        f"  💰 총 잔고: {total_balance:,.4f} USDT",
        f"  💵 사용 가능: {available:,.4f} USDT",
        f"  📈 미실현 PnL: {unrealized:+,.4f} USDT",
        f"  🔒 사용 중 마진: {margin_used:,.4f} USDT",
        f"  ⚠️ 마진 비율: {margin_ratio:.2f}%",
        f"  📊 열린 포지션: {len(active_positions)}개",
    ]

    if active_positions:
        lines.append(f"\n  --- 포지션 목록 ---")
        for p in active_positions:
            amt = float(p.get("positionAmt", 0))
            side = "LONG" if amt > 0 else "SHORT"
            pnl = float(p.get("unrealizedProfit", 0))
            lines.append(f"  {p['symbol']} {side} {abs(amt)} | PnL: {pnl:+,.4f}")

    audit_log("account_summary", {}, get_mode(), "ok", AUDIT_DIR)
    return "\n".join(lines)


@mcp.tool()
async def income_history(symbol: str = "", income_type: str = "", days: int = 7) -> str:
    """
    최근 수익 내역을 조회합니다.

    실현 PnL, 펀딩 수수료, 거래 수수료 등을 볼 수 있습니다.

    income_type 옵션: REALIZED_PNL, FUNDING_FEE, COMMISSION, TRANSFER (비워두면 전체)
    days: 최근 며칠 (기본 7일)
    """
    client = get_client()
    result = await client.get_income(
        symbol=symbol or None,
        income_type=income_type or None,
        limit=100,
    )

    if not result:
        return f"{mode_prefix()}수익 내역이 없습니다."

    # Group by type
    by_type: dict[str, float] = {}
    for r in result:
        t = r.get("incomeType", "OTHER")
        amt = float(r.get("income", 0))
        by_type[t] = by_type.get(t, 0) + amt

    total = sum(by_type.values())
    lines = [f"{mode_prefix()}📜 수익 내역 (최근 {len(result)}건)\n"]
    for t, amt in sorted(by_type.items()):
        label = {
            "REALIZED_PNL": "실현 PnL",
            "FUNDING_FEE": "펀딩 수수료",
            "COMMISSION": "거래 수수료",
            "TRANSFER": "이체",
        }.get(t, t)
        lines.append(f"  {label}: {amt:+,.4f}")
    lines.append(f"\n  합계: {total:+,.4f}")

    audit_log("income_history", {"symbol": symbol, "type": income_type}, get_mode(), "ok", AUDIT_DIR)
    return "\n".join(lines)
