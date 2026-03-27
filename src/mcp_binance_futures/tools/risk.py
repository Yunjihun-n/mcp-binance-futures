"""Risk management tools: SL/TP, leverage, margin type."""

from ..server import mcp, get_client, mode_prefix
from ..client import BinanceAPIError
from ..safety import create_confirmation, verify_confirmation, audit_log
from ..server import AUDIT_DIR, get_mode


async def _place_conditional_order(
    client, symbol: str, side: str, order_type: str,
    stop_price: float, quantity: float | None = None,
    close_position: bool = False, callback_rate: float | None = None,
) -> dict:
    """Place conditional order, fallback to Algo Order API if regular fails."""
    try:
        return await client.place_order(
            symbol=symbol, side=side, order_type=order_type,
            stop_price=stop_price, quantity=quantity,
            close_position=close_position, callback_rate=callback_rate,
        )
    except BinanceAPIError as e:
        if e.code == -4120:  # "Use Algo Order API instead"
            return await client.place_algo_order(
                symbol=symbol, side=side, order_type=order_type,
                trigger_price=stop_price, quantity=quantity,
                close_position=close_position, callback_rate=callback_rate,
            )
        raise


@mcp.tool()
async def set_stop_loss(symbol: str, stop_price: float) -> str:
    """
    포지션에 스탑로스(손절)를 설정합니다.

    현재 열린 포지션의 반대 방향으로 STOP_MARKET 주문을 생성합니다.
    가격이 stop_price에 도달하면 자동으로 포지션을 청산합니다.

    symbol: 거래 심볼 (예: BTCUSDT)
    stop_price: 손절 가격
    """
    client = get_client()
    positions = await client.get_position_risk(symbol.upper())
    active = [p for p in positions if float(p.get("positionAmt", 0)) != 0]

    if not active:
        return f"❌ {symbol.upper()}에 열린 포지션이 없습니다."

    pos = active[0]
    amt = float(pos["positionAmt"])
    entry = float(pos["entryPrice"])
    close_side = "SELL" if amt > 0 else "BUY"

    try:
        resp = await _place_conditional_order(
            client, symbol=symbol.upper(), side=close_side,
            order_type="STOP_MARKET", stop_price=stop_price, close_position=True,
        )
        order_id = resp.get("orderId") or resp.get("algoId", "?")
        audit_log("set_stop_loss", {"symbol": symbol, "stop_price": stop_price}, get_mode(), "ok", AUDIT_DIR)
        return (
            f"{mode_prefix()}✅ 스탑로스 설정 완료\n"
            f"  {symbol.upper()} | 진입가: {entry:,.2f} → 손절가: {stop_price:,.2f}\n"
            f"  주문ID: {order_id}"
        )
    except Exception as e:
        return f"❌ 스탑로스 설정 실패: {e}"


@mcp.tool()
async def set_take_profit(symbol: str, take_price: float) -> str:
    """
    포지션에 익절(테이크프로핏)을 설정합니다.

    가격이 take_price에 도달하면 자동으로 포지션을 청산합니다.

    symbol: 거래 심볼
    take_price: 익절 가격
    """
    client = get_client()
    positions = await client.get_position_risk(symbol.upper())
    active = [p for p in positions if float(p.get("positionAmt", 0)) != 0]

    if not active:
        return f"❌ {symbol.upper()}에 열린 포지션이 없습니다."

    pos = active[0]
    amt = float(pos["positionAmt"])
    entry = float(pos["entryPrice"])
    close_side = "SELL" if amt > 0 else "BUY"

    try:
        resp = await _place_conditional_order(
            client, symbol=symbol.upper(), side=close_side,
            order_type="TAKE_PROFIT_MARKET", stop_price=take_price, close_position=True,
        )
        order_id = resp.get("orderId") or resp.get("algoId", "?")
        audit_log("set_take_profit", {"symbol": symbol, "take_price": take_price}, get_mode(), "ok", AUDIT_DIR)
        return (
            f"{mode_prefix()}✅ 익절 설정 완료\n"
            f"  {symbol.upper()} | 진입가: {entry:,.2f} → 익절가: {take_price:,.2f}\n"
            f"  주문ID: {order_id}"
        )
    except Exception as e:
        return f"❌ 익절 설정 실패: {e}"


@mcp.tool()
async def auto_sl_tp(symbol: str, sl_percent: float, tp_percent: float) -> str:
    """
    진입가 기준으로 자동 손절/익절을 설정합니다.

    포지션 방향에 맞게 자동 계산합니다:
    - 롱: 손절 = 진입가 × (1 - sl%), 익절 = 진입가 × (1 + tp%)
    - 숏: 손절 = 진입가 × (1 + sl%), 익절 = 진입가 × (1 - tp%)

    symbol: 거래 심볼
    sl_percent: 손절 퍼센트 (예: 2.0 = 2%)
    tp_percent: 익절 퍼센트 (예: 5.0 = 5%)
    """
    client = get_client()
    positions = await client.get_position_risk(symbol.upper())
    active = [p for p in positions if float(p.get("positionAmt", 0)) != 0]

    if not active:
        return f"❌ {symbol.upper()}에 열린 포지션이 없습니다."

    pos = active[0]
    amt = float(pos["positionAmt"])
    entry = float(pos["entryPrice"])
    is_long = amt > 0
    close_side = "SELL" if is_long else "BUY"

    if is_long:
        sl_price = round(entry * (1 - sl_percent / 100), 2)
        tp_price = round(entry * (1 + tp_percent / 100), 2)
    else:
        sl_price = round(entry * (1 + sl_percent / 100), 2)
        tp_price = round(entry * (1 - tp_percent / 100), 2)

    results = []

    # Set SL
    try:
        sl_resp = await _place_conditional_order(
            client, symbol=symbol.upper(), side=close_side,
            order_type="STOP_MARKET", stop_price=sl_price, close_position=True,
        )
        sl_id = sl_resp.get("orderId") or sl_resp.get("algoId", "?")
        results.append(f"  ✅ 손절: {sl_price:,.2f} (진입가 대비 -{sl_percent}%) | 주문ID: {sl_id}")
    except Exception as e:
        results.append(f"  ❌ 손절 실패: {e}")

    # Set TP
    try:
        tp_resp = await _place_conditional_order(
            client, symbol=symbol.upper(), side=close_side,
            order_type="TAKE_PROFIT_MARKET", stop_price=tp_price, close_position=True,
        )
        tp_id = tp_resp.get("orderId") or tp_resp.get("algoId", "?")
        results.append(f"  ✅ 익절: {tp_price:,.2f} (진입가 대비 +{tp_percent}%) | 주문ID: {tp_id}")
    except Exception as e:
        results.append(f"  ❌ 익절 실패: {e}")

    side_kr = "롱" if is_long else "숏"
    header = f"{mode_prefix()}🎯 {symbol.upper()} {side_kr} 자동 SL/TP 설정\n  진입가: {entry:,.2f}\n"
    audit_log("auto_sl_tp", {"symbol": symbol, "sl": sl_percent, "tp": tp_percent}, get_mode(), "ok", AUDIT_DIR)
    return header + "\n".join(results)


@mcp.tool()
async def set_trailing_stop(symbol: str, callback_rate: float) -> str:
    """
    트레일링 스탑을 설정합니다.

    가격이 유리한 방향으로 움직인 후, callback_rate% 되돌림 시 포지션을 청산합니다.

    symbol: 거래 심볼
    callback_rate: 콜백 비율 (1.0~5.0%)
    """
    if not 1.0 <= callback_rate <= 5.0:
        return "❌ callback_rate는 1.0~5.0 사이여야 합니다."

    client = get_client()
    positions = await client.get_position_risk(symbol.upper())
    active = [p for p in positions if float(p.get("positionAmt", 0)) != 0]

    if not active:
        return f"❌ {symbol.upper()}에 열린 포지션이 없습니다."

    pos = active[0]
    amt = float(pos["positionAmt"])
    close_side = "SELL" if amt > 0 else "BUY"

    try:
        resp = await _place_conditional_order(
            client, symbol=symbol.upper(), side=close_side,
            order_type="TRAILING_STOP_MARKET", stop_price=0,
            callback_rate=callback_rate, close_position=True,
        )
        order_id = resp.get("orderId") or resp.get("algoId", "?")
        audit_log("set_trailing_stop", {"symbol": symbol, "rate": callback_rate}, get_mode(), "ok", AUDIT_DIR)
        return f"{mode_prefix()}✅ 트레일링 스탑 설정 ({callback_rate}% 콜백) | 주문ID: {order_id}"
    except Exception as e:
        return f"❌ 트레일링 스탑 설정 실패: {e}"


@mcp.tool()
async def change_leverage(symbol: str, leverage: int, confirm_token: str = "") -> str:
    """
    심볼의 레버리지를 변경합니다.

    symbol: 거래 심볼
    leverage: 레버리지 배수 (1~125)
    confirm_token: 확인 토큰 (첫 호출 시 비워두세요)
    """
    symbol = symbol.upper()
    if not 1 <= leverage <= 125:
        return "❌ leverage는 1~125 사이여야 합니다."

    if not confirm_token:
        return create_confirmation(
            "change_leverage", {"symbol": symbol, "leverage": leverage},
            f"{symbol} 레버리지를 {leverage}x로 변경합니다."
        )

    result = verify_confirmation(confirm_token)
    if result is None:
        return "❌ 확인 토큰이 만료되었거나 유효하지 않습니다."

    client = get_client()
    try:
        resp = await client.change_leverage(symbol, leverage)
        audit_log("change_leverage", {"symbol": symbol, "leverage": leverage}, get_mode(), "ok", AUDIT_DIR)
        return f"{mode_prefix()}✅ {symbol} 레버리지 → {leverage}x"
    except Exception as e:
        return f"❌ 레버리지 변경 실패: {e}"


@mcp.tool()
async def change_margin_type(symbol: str, margin_type: str, confirm_token: str = "") -> str:
    """
    마진 타입을 변경합니다.

    symbol: 거래 심볼
    margin_type: ISOLATED (격리) 또는 CROSSED (교차)
    confirm_token: 확인 토큰 (첫 호출 시 비워두세요)
    """
    symbol = symbol.upper()
    margin_type = margin_type.upper()
    if margin_type not in ("ISOLATED", "CROSSED"):
        return "❌ margin_type은 'ISOLATED' 또는 'CROSSED'여야 합니다."

    type_kr = "격리 마진" if margin_type == "ISOLATED" else "교차 마진"

    if not confirm_token:
        return create_confirmation(
            "change_margin_type", {"symbol": symbol, "margin_type": margin_type},
            f"{symbol} 마진 타입을 {type_kr}으로 변경합니다."
        )

    result = verify_confirmation(confirm_token)
    if result is None:
        return "❌ 확인 토큰이 만료되었거나 유효하지 않습니다."

    client = get_client()
    try:
        await client.change_margin_type(symbol, margin_type)
        audit_log("change_margin_type", {"symbol": symbol, "type": margin_type}, get_mode(), "ok", AUDIT_DIR)
        return f"{mode_prefix()}✅ {symbol} → {type_kr}"
    except Exception as e:
        if "No need to change" in str(e):
            return f"{mode_prefix()}ℹ️ {symbol}은 이미 {type_kr}입니다."
        return f"❌ 마진 타입 변경 실패: {e}"
