"""MCP Server entry point for Binance Futures trading."""

import asyncio
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .client import BinanceClient

mcp = FastMCP(
    "Binance Futures Trading",
    instructions=(
        "바이낸스 USDS 마진 선물 거래 도구. "
        "계좌 조회, 주문, SL/TP 설정, 전략 관리, 백테스트를 지원합니다. "
        "기본값은 테스트넷(testnet)이며, 실거래는 명시적으로 전환해야 합니다."
    ),
)

# --- Global state ---
_state = {
    "mode": "testnet",  # "testnet" or "live"
    "client": None,
}
_state_lock = asyncio.Lock()

STRATEGIES_DIR = Path(__file__).parent.parent.parent / "strategies"
AUDIT_DIR = STRATEGIES_DIR


def get_client() -> BinanceClient:
    """Get or create the Binance client using env vars from MCP config."""
    if _state["client"] is None:
        mode = _state["mode"]
        if mode == "testnet":
            api_key = os.environ.get("BINANCE_TESTNET_API_KEY", "")
            api_secret = os.environ.get("BINANCE_TESTNET_SECRET_KEY", "")
        else:
            api_key = os.environ.get("BINANCE_LIVE_API_KEY", "")
            api_secret = os.environ.get("BINANCE_LIVE_SECRET_KEY", "")

        if not api_key or not api_secret:
            raise ValueError(
                f"API 키가 설정되지 않았습니다. MCP 설정의 env에 "
                f"{'BINANCE_TESTNET_API_KEY/BINANCE_TESTNET_SECRET_KEY' if mode == 'testnet' else 'BINANCE_LIVE_API_KEY/BINANCE_LIVE_SECRET_KEY'}를 추가하세요."
            )
        _state["client"] = BinanceClient(api_key, api_secret, mode)
    return _state["client"]


def get_mode() -> str:
    return _state["mode"]


def mode_prefix() -> str:
    m = _state["mode"]
    return "[TESTNET] " if m == "testnet" else "[⚠️ LIVE] "


# --- Mode switching tool ---
@mcp.tool()
async def switch_mode(mode: str, confirm_token: str = "") -> str:
    """
    거래 모드를 전환합니다 (testnet 또는 live).

    - testnet: 테스트넷에서 가상 거래 (기본값, 안전)
    - live: 실제 자금으로 거래 (주의!)

    live로 전환 시 확인 토큰이 필요합니다.
    """
    from .safety import create_confirmation, verify_confirmation

    mode = mode.lower()
    if mode not in ("testnet", "live"):
        return "❌ 유효한 모드: 'testnet' 또는 'live'"

    if mode == "live" and not confirm_token:
        return create_confirmation(
            "switch_mode", {"mode": "live"},
            "⚠️ LIVE 모드로 전환합니다. 실제 자금이 사용됩니다!"
        )

    if mode == "live" and confirm_token:
        result = verify_confirmation(confirm_token)
        if result is None:
            return "❌ 확인 토큰이 만료되었거나 유효하지 않습니다. 다시 시도하세요."

    # Close existing client
    if _state["client"]:
        await _state["client"].close()
        _state["client"] = None

    _state["mode"] = mode
    return f"✅ 모드가 '{mode}'(으)로 전환되었습니다. {'테스트넷 거래입니다.' if mode == 'testnet' else '⚠️ 실제 자금 거래입니다!'}"


# Import tool modules to register them
from .tools import account, market, trading, risk, strategy, backtest  # noqa: E402, F401


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
