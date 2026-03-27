"""Pydantic models for strategy configs and data types."""

from datetime import datetime
from pydantic import BaseModel, Field


class EntryCondition(BaseModel):
    """Simple price-based entry condition."""
    type: str = Field(description="Condition type: 'price_above', 'price_below', 'price_change_pct'")
    value: float = Field(description="Threshold value (price or percentage)")
    description: str = Field(default="", description="Human-readable description")


class StrategyConfig(BaseModel):
    """Trading strategy configuration."""
    name: str
    symbol: str
    description: str = ""
    side: str = Field(description="BUY or SELL")
    leverage: int = Field(default=1, ge=1, le=125)
    margin_type: str = Field(default="CROSSED", description="ISOLATED or CROSSED")
    position_size: float = Field(description="Order quantity")
    order_type: str = Field(default="MARKET", description="MARKET or LIMIT")
    limit_price: float | None = Field(default=None, description="Limit price if order_type=LIMIT")
    entry_conditions: list[EntryCondition] = Field(default_factory=list)
    sl_percent: float | None = Field(default=None, description="Stop-loss % from entry")
    tp_percent: float | None = Field(default=None, description="Take-profit % from entry")
    trailing_stop_callback: float | None = Field(default=None, description="Trailing stop callback rate %")
    max_hold_candles: int = Field(default=50, ge=1, description="Max candles to hold before timeout exit")
    fee_rate: float = Field(default=0.0004, ge=0, description="Trading fee rate per side (default 0.04%)")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class BacktestResult(BaseModel):
    """Backtest result summary."""
    strategy_name: str
    symbol: str
    period: str
    interval: str
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    max_drawdown: float
    sharpe_ratio: float | None = None
    avg_trade_pnl: float
    best_trade: float
    worst_trade: float
