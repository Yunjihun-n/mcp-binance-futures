"""Strategy management tools: CRUD for local JSON strategy configs."""

import json
from datetime import datetime
from pathlib import Path

from ..server import mcp, mode_prefix
from ..models import StrategyConfig
from ..server import STRATEGIES_DIR


def _strategies_dir() -> Path:
    STRATEGIES_DIR.mkdir(parents=True, exist_ok=True)
    return STRATEGIES_DIR


def _load_strategy(name: str) -> StrategyConfig | None:
    path = _strategies_dir() / f"{name}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return StrategyConfig(**data)


def _save_strategy(config: StrategyConfig):
    path = _strategies_dir() / f"{config.name}.json"
    path.write_text(json.dumps(config.model_dump(), indent=2, ensure_ascii=False))


@mcp.tool()
async def list_strategies() -> str:
    """
    저장된 전략 목록을 보여줍니다.

    각 전략의 이름, 심볼, 설명, SL/TP 설정을 요약합니다.
    """
    d = _strategies_dir()
    files = sorted(d.glob("*.json"))

    if not files:
        return "📂 저장된 전략이 없습니다. create_strategy로 새 전략을 만들어보세요."

    lines = [f"📂 저장된 전략 ({len(files)}개)\n"]
    for f in files:
        try:
            config = StrategyConfig(**json.loads(f.read_text()))
            sl = f"SL:{config.sl_percent}%" if config.sl_percent else "SL:없음"
            tp = f"TP:{config.tp_percent}%" if config.tp_percent else "TP:없음"
            lines.append(
                f"  📌 {config.name} | {config.symbol} {config.side} | "
                f"수량:{config.position_size} | 레버리지:{config.leverage}x | {sl} {tp}"
            )
            if config.description:
                lines.append(f"     └ {config.description}")
        except Exception:
            lines.append(f"  ⚠️ {f.stem} (파일 읽기 오류)")

    return "\n".join(lines)


@mcp.tool()
async def view_strategy(name: str) -> str:
    """
    전략의 상세 설정을 보여줍니다.

    name: 전략 이름
    """
    config = _load_strategy(name)
    if config is None:
        return f"❌ '{name}' 전략을 찾을 수 없습니다. list_strategies로 목록을 확인하세요."

    side_kr = "매수(롱)" if config.side == "BUY" else "매도(숏)"
    type_kr = "시장가" if config.order_type == "MARKET" else f"지정가 {config.limit_price}"
    margin_kr = "교차" if config.margin_type == "CROSSED" else "격리"

    lines = [
        f"📌 전략: {config.name}",
        f"  설명: {config.description or '(없음)'}",
        f"",
        f"  심볼: {config.symbol}",
        f"  방향: {side_kr}",
        f"  주문방식: {type_kr}",
        f"  수량: {config.position_size}",
        f"  레버리지: {config.leverage}x ({margin_kr} 마진)",
        f"",
        f"  손절: {config.sl_percent}%" if config.sl_percent else "  손절: 없음",
        f"  익절: {config.tp_percent}%" if config.tp_percent else "  익절: 없음",
    ]
    if config.trailing_stop_callback:
        lines.append(f"  트레일링스탑: {config.trailing_stop_callback}% 콜백")

    if config.entry_conditions:
        lines.append(f"\n  진입 조건:")
        for c in config.entry_conditions:
            lines.append(f"    - {c.type}: {c.value} ({c.description})")

    lines.append(f"\n  생성: {config.created_at}")
    lines.append(f"  수정: {config.updated_at}")

    return "\n".join(lines)


@mcp.tool()
async def create_strategy(
    name: str,
    symbol: str,
    side: str,
    position_size: float,
    leverage: int = 1,
    order_type: str = "MARKET",
    limit_price: float = 0,
    sl_percent: float = 0,
    tp_percent: float = 0,
    trailing_stop_callback: float = 0,
    margin_type: str = "CROSSED",
    description: str = "",
) -> str:
    """
    새 트레이딩 전략을 생성합니다.

    name: 전략 이름 (영문, 중복 불가)
    symbol: 거래 심볼 (예: BTCUSDT)
    side: BUY (롱) 또는 SELL (숏)
    position_size: 주문 수량
    leverage: 레버리지 (기본 1x)
    order_type: MARKET (시장가) 또는 LIMIT (지정가)
    limit_price: 지정가 (order_type=LIMIT일 때)
    sl_percent: 손절 % (0이면 없음)
    tp_percent: 익절 % (0이면 없음)
    trailing_stop_callback: 트레일링스탑 콜백 % (0이면 없음)
    margin_type: CROSSED (교차) 또는 ISOLATED (격리)
    description: 전략 설명
    """
    if _load_strategy(name) is not None:
        return f"❌ '{name}' 전략이 이미 존재합니다. 다른 이름을 사용하세요."

    config = StrategyConfig(
        name=name,
        symbol=symbol.upper(),
        side=side.upper(),
        position_size=position_size,
        leverage=leverage,
        order_type=order_type.upper(),
        limit_price=limit_price if limit_price > 0 else None,
        sl_percent=sl_percent if sl_percent > 0 else None,
        tp_percent=tp_percent if tp_percent > 0 else None,
        trailing_stop_callback=trailing_stop_callback if trailing_stop_callback > 0 else None,
        margin_type=margin_type.upper(),
        description=description,
    )
    _save_strategy(config)
    return f"✅ 전략 '{name}' 생성 완료!\n\n" + await view_strategy(name)


@mcp.tool()
async def modify_strategy(name: str, updates: str) -> str:
    """
    기존 전략의 설정을 수정합니다.

    name: 수정할 전략 이름
    updates: 수정할 필드를 JSON 형식으로 (예: {"sl_percent": 3.0, "leverage": 10})

    수정 가능한 필드:
    symbol, side, position_size, leverage, order_type, limit_price,
    sl_percent, tp_percent, trailing_stop_callback, margin_type, description
    """
    config = _load_strategy(name)
    if config is None:
        return f"❌ '{name}' 전략을 찾을 수 없습니다."

    try:
        update_dict = json.loads(updates)
    except json.JSONDecodeError:
        return "❌ updates는 유효한 JSON이어야 합니다. 예: {\"sl_percent\": 3.0}"

    allowed_fields = {
        "symbol", "side", "position_size", "leverage", "order_type", "limit_price",
        "sl_percent", "tp_percent", "trailing_stop_callback", "margin_type", "description",
    }
    invalid = set(update_dict.keys()) - allowed_fields
    if invalid:
        return f"❌ 수정할 수 없는 필드: {invalid}. 가능: {allowed_fields}"

    data = config.model_dump()
    data.update(update_dict)
    data["updated_at"] = datetime.now().isoformat()

    new_config = StrategyConfig(**data)
    _save_strategy(new_config)

    changes = ", ".join(f"{k}={v}" for k, v in update_dict.items())
    return f"✅ 전략 '{name}' 수정 완료 ({changes})\n\n" + await view_strategy(name)


@mcp.tool()
async def delete_strategy(name: str) -> str:
    """
    전략을 삭제합니다.

    name: 삭제할 전략 이름
    """
    path = _strategies_dir() / f"{name}.json"
    if not path.exists():
        return f"❌ '{name}' 전략을 찾을 수 없습니다."

    path.unlink()
    return f"✅ 전략 '{name}' 삭제 완료."
