"""Backtest engine: simulates strategy on historical OHLCV data."""

import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from ..models import StrategyConfig, BacktestResult


async def run_backtest_engine(
    config: StrategyConfig,
    symbol: str,
    data_path: str = "",
    start_date: str = "",
    end_date: str = "",
    interval: str = "1h",
) -> BacktestResult:
    """Run backtest on OHLCV data."""

    # Load data
    if data_path:
        df = _load_local_data(data_path)
    else:
        df = await _load_api_data(symbol, interval, start_date, end_date)

    if df.empty or len(df) < 5:
        raise ValueError("데이터가 부족합니다 (최소 5개 캔들 필요)")

    # Simulate
    trades = _simulate(config, df)

    # Calculate stats
    return _calculate_stats(config.name, symbol, df, trades, interval)


def _load_local_data(path: str) -> pd.DataFrame:
    """Load OHLCV data from local CSV or JSON."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {path}")

    if p.suffix == ".csv":
        df = pd.read_csv(p)
    elif p.suffix == ".json":
        df = pd.DataFrame(json.loads(p.read_text()))
    else:
        raise ValueError(f"지원하지 않는 형식: {p.suffix} (csv 또는 json만 가능)")

    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"필수 컬럼 누락: {missing}")

    df = df.sort_values("timestamp").reset_index(drop=True)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


async def _load_api_data(
    symbol: str, interval: str, start_date: str, end_date: str
) -> pd.DataFrame:
    """Load OHLCV data from Binance API."""
    from ..server import get_client

    client = get_client()

    start_ts = None
    end_ts = None
    if start_date:
        start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
    if end_date:
        end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)

    # Fetch up to 1500 candles
    all_klines = []
    limit = 1500

    klines = await client.get_klines(
        symbol=symbol, interval=interval, limit=limit,
        start_time=start_ts, end_time=end_ts,
    )
    all_klines.extend(klines)

    if not all_klines:
        raise ValueError(f"{symbol} {interval} 데이터를 가져올 수 없습니다.")

    # Parse klines: [open_time, open, high, low, close, volume, ...]
    rows = []
    for k in all_klines:
        rows.append({
            "timestamp": k[0],
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
        })

    df = pd.DataFrame(rows)
    return df


def _calc_pnl(entry_price: float, exit_price: float, config: StrategyConfig, is_long: bool) -> float:
    """Calculate PnL including fees."""
    notional = entry_price * config.position_size * config.leverage
    entry_fee = notional * config.fee_rate
    exit_notional = exit_price * config.position_size * config.leverage
    exit_fee = exit_notional * config.fee_rate
    if is_long:
        raw_pnl = (exit_price - entry_price) * config.position_size * config.leverage
    else:
        raw_pnl = (entry_price - exit_price) * config.position_size * config.leverage
    return raw_pnl - entry_fee - exit_fee


def _simulate(config: StrategyConfig, df: pd.DataFrame) -> list[dict]:
    """Simple candle-based simulation with fees."""
    trades = []
    in_position = False
    entry_price = 0.0
    entry_idx = 0
    is_long = config.side == "BUY"
    max_hold = config.max_hold_candles

    for i in range(1, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i - 1]

        if not in_position:
            # Entry: check conditions
            should_enter = True

            for cond in config.entry_conditions:
                if cond.type == "price_above" and row["close"] <= cond.value:
                    should_enter = False
                elif cond.type == "price_below" and row["close"] >= cond.value:
                    should_enter = False
                elif cond.type == "price_change_pct":
                    pct = (row["close"] - prev["close"]) / prev["close"] * 100
                    if is_long and pct < cond.value:
                        should_enter = False
                    elif not is_long and pct > -cond.value:
                        should_enter = False

            # If no conditions, enter periodically to test SL/TP
            if not config.entry_conditions:
                if i % max(len(df) // 50, 3) != 0:
                    should_enter = False

            if should_enter:
                in_position = True
                entry_price = row["open"]
                entry_idx = i

        else:
            # Check SL/TP
            sl_hit = False
            tp_hit = False
            exit_price = row["close"]

            if is_long:
                if config.sl_percent:
                    sl_price = entry_price * (1 - config.sl_percent / 100)
                    if row["low"] <= sl_price:
                        exit_price = sl_price
                        sl_hit = True
                if config.tp_percent and not sl_hit:
                    tp_price = entry_price * (1 + config.tp_percent / 100)
                    if row["high"] >= tp_price:
                        exit_price = tp_price
                        tp_hit = True
            else:
                if config.sl_percent:
                    sl_price = entry_price * (1 + config.sl_percent / 100)
                    if row["high"] >= sl_price:
                        exit_price = sl_price
                        sl_hit = True
                if config.tp_percent and not sl_hit:
                    tp_price = entry_price * (1 - config.tp_percent / 100)
                    if row["low"] <= tp_price:
                        exit_price = tp_price
                        tp_hit = True

            if sl_hit or tp_hit or (i - entry_idx >= max_hold):
                pnl = _calc_pnl(entry_price, exit_price, config, is_long)
                trades.append({
                    "entry_idx": entry_idx,
                    "exit_idx": i,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "pnl": pnl,
                    "reason": "SL" if sl_hit else ("TP" if tp_hit else "timeout"),
                })
                in_position = False

    # Close remaining position
    if in_position:
        last = df.iloc[-1]
        pnl = _calc_pnl(entry_price, last["close"], config, is_long)
        trades.append({
            "entry_idx": entry_idx,
            "exit_idx": len(df) - 1,
            "entry_price": entry_price,
            "exit_price": last["close"],
            "pnl": pnl,
            "reason": "end",
        })

    return trades


def _calculate_stats(
    name: str, symbol: str, df: pd.DataFrame, trades: list[dict], interval: str
) -> BacktestResult:
    """Calculate backtest statistics."""
    if not trades:
        start_ts = df.iloc[0]["timestamp"]
        end_ts = df.iloc[-1]["timestamp"]
        period = f"{datetime.fromtimestamp(start_ts/1000).strftime('%Y-%m-%d')} ~ {datetime.fromtimestamp(end_ts/1000).strftime('%Y-%m-%d')}"
        return BacktestResult(
            strategy_name=name, symbol=symbol, period=period, interval=interval,
            total_trades=0, winning_trades=0, losing_trades=0, win_rate=0,
            total_pnl=0, max_drawdown=0, sharpe_ratio=None,
            avg_trade_pnl=0, best_trade=0, worst_trade=0,
        )

    pnls = [t["pnl"] for t in trades]
    winning = [p for p in pnls if p > 0]
    losing = [p for p in pnls if p <= 0]

    # Max drawdown (from peak equity)
    cumulative = np.cumsum(pnls)
    peak = np.maximum.accumulate(cumulative)
    drawdowns = peak - cumulative
    max_dd = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0
    total_pnl = sum(pnls)
    # Drawdown % relative to peak equity (not total PnL)
    peak_equity = float(np.max(peak)) if len(peak) > 0 else 1.0
    max_dd_pct = (max_dd / max(peak_equity, 0.01)) * 100 if peak_equity > 0 else 0

    # Sharpe (annualized, assuming daily returns)
    sharpe = None
    if len(pnls) > 1:
        arr = np.array(pnls)
        if arr.std() > 0:
            sharpe = float(arr.mean() / arr.std() * math.sqrt(252))

    start_ts = df.iloc[0]["timestamp"]
    end_ts = df.iloc[-1]["timestamp"]
    period = f"{datetime.fromtimestamp(start_ts/1000).strftime('%Y-%m-%d')} ~ {datetime.fromtimestamp(end_ts/1000).strftime('%Y-%m-%d')}"

    return BacktestResult(
        strategy_name=name,
        symbol=symbol,
        period=period,
        interval=interval,
        total_trades=len(trades),
        winning_trades=len(winning),
        losing_trades=len(losing),
        win_rate=len(winning) / len(trades) * 100,
        total_pnl=round(total_pnl, 4),
        max_drawdown=round(max_dd_pct, 2),
        sharpe_ratio=round(sharpe, 2) if sharpe else None,
        avg_trade_pnl=round(total_pnl / len(trades), 4),
        best_trade=round(max(pnls), 4),
        worst_trade=round(min(pnls), 4),
    )
