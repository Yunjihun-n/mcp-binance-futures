"""Backtest tools: run strategy backtests on historical data."""

import json
from pathlib import Path

from ..server import mcp
from ..models import StrategyConfig, BacktestResult
from ..backtest.engine import run_backtest_engine
from ..server import STRATEGIES_DIR


def _load_strategy(name: str) -> StrategyConfig | None:
    path = STRATEGIES_DIR / f"{name}.json"
    if not path.exists():
        return None
    return StrategyConfig(**json.loads(path.read_text()))


@mcp.tool()
async def run_backtest(
    strategy_name: str,
    symbol: str = "",
    data_path: str = "",
    start_date: str = "",
    end_date: str = "",
    interval: str = "1h",
) -> str:
    """
    전략을 과거 데이터로 백테스트합니다.

    strategy_name: 백테스트할 전략 이름 (create_strategy로 생성한 것)
    symbol: 심볼 (비워두면 전략의 심볼 사용)
    data_path: 로컬 CSV/JSON 데이터 경로 (비워두면 바이낸스 API에서 가져옴)
    start_date: 시작일 (YYYY-MM-DD, API 사용 시)
    end_date: 종료일 (YYYY-MM-DD, API 사용 시)
    interval: 캔들 간격 (1m, 5m, 15m, 1h, 4h, 1d 등)

    📊 데이터 준비 방법:
    - CSV 파일: timestamp, open, high, low, close, volume 컬럼 필요
    - JSON 파일: 위 필드를 가진 객체 배열
    - 비워두면 바이낸스에서 최근 500개 캔들을 가져옵니다
    """
    config = _load_strategy(strategy_name)
    if config is None:
        return f"❌ '{strategy_name}' 전략을 찾을 수 없습니다. list_strategies로 확인하세요."

    test_symbol = symbol.upper() if symbol else config.symbol

    try:
        result = await run_backtest_engine(
            config=config,
            symbol=test_symbol,
            data_path=data_path,
            start_date=start_date,
            end_date=end_date,
            interval=interval,
        )
    except Exception as e:
        return f"❌ 백테스트 실패: {e}"

    pnl_emoji = "📈" if result.total_pnl > 0 else "📉"
    lines = [
        f"{pnl_emoji} 백테스트 결과: {strategy_name} ({test_symbol})",
        f"  기간: {result.period} | 간격: {result.interval}",
        f"",
        f"  총 거래: {result.total_trades}회",
        f"  승/패: {result.winning_trades}승 {result.losing_trades}패",
        f"  승률: {result.win_rate:.1f}%",
        f"",
        f"  총 PnL: {result.total_pnl:+,.4f} USDT",
        f"  평균 거래 PnL: {result.avg_trade_pnl:+,.4f}",
        f"  최고 수익: {result.best_trade:+,.4f}",
        f"  최대 손실: {result.worst_trade:+,.4f}",
        f"  최대 낙폭: {result.max_drawdown:.2f}%",
    ]
    if result.sharpe_ratio is not None:
        lines.append(f"  샤프 비율: {result.sharpe_ratio:.2f}")

    return "\n".join(lines)


@mcp.tool()
async def quick_backtest(strategy_name: str, symbol: str = "", days: int = 7) -> str:
    """
    최근 N일 데이터로 빠른 백테스트를 실행합니다.

    바이낸스 API에서 최근 데이터를 가져와 간단히 테스트합니다.

    strategy_name: 전략 이름
    symbol: 심볼 (비워두면 전략 심볼 사용)
    days: 최근 며칠 (기본 7일)
    """
    from datetime import datetime, timedelta
    end = datetime.now()
    start = end - timedelta(days=days)

    return await run_backtest(
        strategy_name=strategy_name,
        symbol=symbol,
        start_date=start.strftime("%Y-%m-%d"),
        end_date=end.strftime("%Y-%m-%d"),
        interval="1h",
    )


@mcp.tool()
async def backtest_data_guide() -> str:
    """
    백테스트용 데이터 준비 가이드를 보여줍니다.

    어떤 형식으로 데이터를 준비해야 하는지 설명합니다.
    """
    return """📖 백테스트 데이터 준비 가이드

1️⃣ CSV 형식 (권장)
   파일 예: /path/to/btcusdt_1h.csv

   필수 컬럼:
   timestamp,open,high,low,close,volume
   1711324800000,65000.0,65500.0,64800.0,65200.0,1234.5
   1711328400000,65200.0,65800.0,65100.0,65700.0,987.3
   ...

   - timestamp: 밀리초 Unix timestamp
   - OHLCV: 숫자형

2️⃣ JSON 형식
   파일 예: /path/to/btcusdt_1h.json

   [
     {"timestamp": 1711324800000, "open": 65000, "high": 65500, "low": 64800, "close": 65200, "volume": 1234.5},
     ...
   ]

3️⃣ 바이낸스에서 데이터 다운로드
   데이터가 없으면 run_backtest에서 자동으로 바이낸스 API에서 가져옵니다.
   (최대 1500개 캔들, 약 62일분 1시간봉)

4️⃣ 사용법
   run_backtest(strategy_name="my_strategy", data_path="/path/to/data.csv")
"""
