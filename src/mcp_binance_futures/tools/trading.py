"""Trading tools: place/cancel/modify orders."""

from ..server import mcp, get_client, mode_prefix
from ..safety import create_confirmation, verify_confirmation, audit_log
from ..server import AUDIT_DIR, get_mode


@mcp.tool()
async def place_order(
    symbol: str,
    side: str,
    order_type: str = "MARKET",
    quantity: float = 0,
    price: float = 0,
    reduce_only: bool = False,
    confirm_token: str = "",
) -> str:
    """
    선물 주문을 생성합니다.

    symbol: 거래 심볼 (예: BTCUSDT, ETHUSDT)
    side: BUY (매수/롱) 또는 SELL (매도/숏)
    order_type: MARKET (시장가) 또는 LIMIT (지정가)
    quantity: 주문 수량
    price: 지정가 주문 시 가격 (시장가면 불필요)
    reduce_only: true이면 포지션 축소만 (기본 false)
    confirm_token: 확인 토큰 (첫 호출 시 비워두세요)

    ⚠️ 2단계 확인: 처음 호출하면 확인 요청을 받고, 토큰으로 재호출하면 실행됩니다.
    """
    symbol = symbol.upper()
    side = side.upper()
    order_type = order_type.upper()

    if side not in ("BUY", "SELL"):
        return "❌ side는 'BUY' 또는 'SELL'이어야 합니다."
    if order_type not in ("MARKET", "LIMIT"):
        return "❌ order_type은 'MARKET' 또는 'LIMIT'이어야 합니다."
    if quantity <= 0:
        return "❌ quantity는 0보다 커야 합니다."
    if order_type == "LIMIT" and price <= 0:
        return "❌ 지정가 주문 시 price를 입력하세요."

    side_kr = "매수(롱)" if side == "BUY" else "매도(숏)"
    type_kr = "시장가" if order_type == "MARKET" else f"지정가 {price:,.2f}"
    summary = f"{symbol} {quantity} {side_kr} {type_kr} 주문"

    if not confirm_token:
        return create_confirmation("place_order", {
            "symbol": symbol, "side": side, "type": order_type,
            "quantity": quantity, "price": price,
        }, summary)

    result = verify_confirmation(confirm_token)
    if result is None:
        return "❌ 확인 토큰이 만료되었거나 유효하지 않습니다. 다시 시도하세요."

    client = get_client()
    try:
        resp = await client.place_order(
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price if order_type == "LIMIT" else None,
            time_in_force="GTC" if order_type == "LIMIT" else None,
            reduce_only=reduce_only,
        )
        order_id = resp.get("orderId", "?")
        status = resp.get("status", "?")
        audit_log("place_order", {"symbol": symbol, "side": side, "qty": quantity}, get_mode(), "ok", AUDIT_DIR)
        return f"{mode_prefix()}✅ 주문 완료!\n  주문ID: {order_id} | 상태: {status}\n  {summary}"
    except Exception as e:
        audit_log("place_order", {"symbol": symbol}, get_mode(), f"error: {e}", AUDIT_DIR)
        return f"❌ 주문 실패: {e}"


@mcp.tool()
async def cancel_order(symbol: str, order_id: int) -> str:
    """
    특정 주문을 취소합니다.

    symbol: 거래 심볼
    order_id: 취소할 주문 ID (view_open_orders로 확인 가능)
    """
    client = get_client()
    try:
        resp = await client.cancel_order(symbol.upper(), order_id)
        audit_log("cancel_order", {"symbol": symbol, "order_id": order_id}, get_mode(), "ok", AUDIT_DIR)
        return f"{mode_prefix()}✅ 주문 {order_id} 취소 완료 ({symbol.upper()})"
    except Exception as e:
        return f"❌ 취소 실패: {e}"


@mcp.tool()
async def cancel_all_orders(symbol: str, confirm_token: str = "") -> str:
    """
    해당 심볼의 모든 열린 주문을 취소합니다.

    symbol: 거래 심볼 (예: BTCUSDT)
    confirm_token: 확인 토큰 (첫 호출 시 비워두세요)
    """
    symbol = symbol.upper()

    if not confirm_token:
        return create_confirmation(
            "cancel_all_orders", {"symbol": symbol},
            f"{symbol}의 모든 열린 주문을 취소합니다."
        )

    result = verify_confirmation(confirm_token)
    if result is None:
        return "❌ 확인 토큰이 만료되었거나 유효하지 않습니다."

    client = get_client()
    try:
        await client.cancel_all_orders(symbol)
        audit_log("cancel_all_orders", {"symbol": symbol}, get_mode(), "ok", AUDIT_DIR)
        return f"{mode_prefix()}✅ {symbol}의 모든 열린 주문이 취소되었습니다."
    except Exception as e:
        return f"❌ 전체 취소 실패: {e}"


@mcp.tool()
async def view_open_orders(symbol: str = "") -> str:
    """
    열린 주문 목록을 조회합니다.

    symbol을 비워두면 모든 심볼의 열린 주문을 보여줍니다.
    """
    client = get_client()
    orders = await client.get_open_orders(symbol.upper() if symbol else None)

    if not orders:
        return f"{mode_prefix()}열린 주문이 없습니다."

    lines = [f"{mode_prefix()}📋 열린 주문 ({len(orders)}건)\n"]
    for o in orders:
        oid = o.get("orderId", "?")
        sym = o.get("symbol", "?")
        side = o.get("side", "?")
        otype = o.get("type", "?")
        price = o.get("price", "0")
        stop = o.get("stopPrice", "0")
        qty = o.get("origQty", "0")
        status = o.get("status", "?")

        price_str = f"가격:{float(price):,.2f}" if float(price) > 0 else ""
        stop_str = f"스탑:{float(stop):,.2f}" if float(stop) > 0 else ""
        lines.append(
            f"  [{oid}] {sym} {side} {otype} | 수량:{qty} {price_str} {stop_str} | {status}"
        )

    audit_log("view_open_orders", {"symbol": symbol}, get_mode(), "ok", AUDIT_DIR)
    return "\n".join(lines)


@mcp.tool()
async def modify_order(
    symbol: str, order_id: int,
    quantity: float = 0, price: float = 0,
) -> str:
    """
    열린 주문을 수정합니다.

    symbol: 거래 심볼
    order_id: 수정할 주문 ID
    quantity: 새 수량 (0이면 변경 안 함)
    price: 새 가격 (0이면 변경 안 함)
    """
    client = get_client()
    try:
        resp = await client.modify_order(
            symbol.upper(), order_id,
            quantity=quantity if quantity > 0 else None,
            price=price if price > 0 else None,
        )
        audit_log("modify_order", {"symbol": symbol, "order_id": order_id}, get_mode(), "ok", AUDIT_DIR)
        return f"{mode_prefix()}✅ 주문 {order_id} 수정 완료"
    except Exception as e:
        return f"❌ 수정 실패: {e}"
