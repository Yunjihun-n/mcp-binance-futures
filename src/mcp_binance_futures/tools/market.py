"""Market data tools: price, 24hr stats, funding rate."""

from ..server import mcp, get_client, mode_prefix
from ..safety import audit_log
from ..server import AUDIT_DIR, get_mode


@mcp.tool()
async def get_price(symbol: str) -> str:
    """
    심볼의 현재 가격을 조회합니다.

    예: symbol='BTCUSDT' → 비트코인 현재가
    """
    client = get_client()
    data = await client.get_price(symbol.upper())
    price = float(data.get("price", 0))

    audit_log("get_price", {"symbol": symbol}, get_mode(), "ok", AUDIT_DIR)
    return f"{mode_prefix()}{symbol.upper()} 현재가: {price:,.4f}"


@mcp.tool()
async def get_market_stats(symbol: str) -> str:
    """
    심볼의 24시간 시장 통계를 조회합니다.

    가격 변동, 고가/저가, 거래량 등을 보여줍니다.
    예: symbol='ETHUSDT'
    """
    client = get_client()
    data = await client.get_ticker_24hr(symbol.upper())

    price = float(data.get("lastPrice", 0))
    change = float(data.get("priceChange", 0))
    change_pct = float(data.get("priceChangePercent", 0))
    high = float(data.get("highPrice", 0))
    low = float(data.get("lowPrice", 0))
    volume = float(data.get("volume", 0))
    quote_vol = float(data.get("quoteVolume", 0))

    lines = [
        f"{mode_prefix()}📊 {symbol.upper()} 24시간 통계",
        f"",
        f"  현재가: {price:,.4f}",
        f"  변동: {change:+,.4f} ({change_pct:+.2f}%)",
        f"  고가: {high:,.4f} | 저가: {low:,.4f}",
        f"  거래량: {volume:,.2f} | 거래대금: {quote_vol:,.0f}",
    ]

    audit_log("get_market_stats", {"symbol": symbol}, get_mode(), "ok", AUDIT_DIR)
    return "\n".join(lines)


@mcp.tool()
async def get_funding_rate(symbol: str, limit: int = 5) -> str:
    """
    펀딩레이트를 조회합니다.

    선물 시장의 펀딩레이트 (양수: 롱이 숏에게 지불, 음수: 숏이 롱에게 지불).
    limit: 최근 몇 건 (기본 5건)
    """
    client = get_client()
    data = await client.get_funding_rate(symbol.upper(), limit)

    if not data:
        return f"{mode_prefix()}{symbol.upper()} 펀딩레이트 데이터가 없습니다."

    lines = [f"{mode_prefix()}💱 {symbol.upper()} 펀딩레이트 (최근 {len(data)}건)\n"]
    for d in data:
        rate = float(d.get("fundingRate", 0))
        ts = d.get("fundingTime", 0)
        from datetime import datetime
        time_str = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M") if ts else "?"
        direction = "롱→숏" if rate > 0 else "숏→롱"
        lines.append(f"  {time_str} | {rate*100:+.4f}% ({direction})")

    audit_log("get_funding_rate", {"symbol": symbol}, get_mode(), "ok", AUDIT_DIR)
    return "\n".join(lines)
