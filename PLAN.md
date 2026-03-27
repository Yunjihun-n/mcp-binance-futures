# MCP Binance Futures Trading Server - 구현 계획

## 개요
바이낸스 USDS-마진 선물 트레이딩용 MCP 서버. 비개발자가 Claude Code/Desktop에서 자연어로 선물 거래를 관리할 수 있도록 설계.

## 결정 사항 (2026-03-26)

1. **전략 범위**: 단순 (가격 기반 조건 + SL/TP/레버리지)
2. **심볼**: 멀티 심볼 자유 지정
3. **백테스트**: 사용자 로컬 데이터. MCP는 데이터 포맷/저장 방법만 안내
4. **API 키**: MCP config의 env로 입력받음 (누구나 사용 가능하도록)
5. **2단계 분리**: Phase A(단순 매수매도/계좌관리) → Phase B(백테스트/전략)

## 디렉토리 구조

```
mcp-binance-futures/
├── pyproject.toml
├── src/
│   └── mcp_binance_futures/
│       ├── __init__.py
│       ├── server.py              # FastMCP 엔트리포인트
│       ├── client.py              # 바이낸스 REST API 클라이언트 (async httpx)
│       ├── models.py              # Pydantic 모델
│       ├── safety.py              # 안전장치 (확인 게이트, 모드 가드, 제한)
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── account.py         # 잔고, 포지션, 계좌 요약
│       │   ├── trading.py         # 주문 생성/취소/수정
│       │   ├── market.py          # 가격, 펀딩레이트, 24시간 통계
│       │   ├── risk.py            # SL/TP, 레버리지, 마진타입
│       │   ├── strategy.py        # 전략 CRUD
│       │   └── backtest.py        # 백테스트 실행
│       └── backtest/
│           ├── engine.py          # 백테스트 엔진
│           └── data_loader.py     # Kline 데이터 로더
└── strategies/                    # 사용자 전략 JSON 저장소
```

## MCP 도구 목록 (22개)

### 계좌 (4개)
| 도구명 | 설명 | 핵심 파라미터 |
|--------|------|--------------|
| `check_balance` | 선물 지갑 잔고 확인 | `asset?` |
| `view_positions` | 열린 포지션 확인 (진입가, PnL, 청산가) | `symbol?` |
| `account_summary` | 원샷 계좌 요약 | 없음 |
| `income_history` | 수익 내역 (실현PnL, 펀딩, 수수료) | `symbol?`, `days?` |

### 시장 데이터 (3개)
| 도구명 | 설명 | 핵심 파라미터 |
|--------|------|--------------|
| `get_price` | 현재가 조회 | `symbol` |
| `get_market_stats` | 24시간 변동/거래량/고저 | `symbol` |
| `get_funding_rate` | 펀딩레이트 조회 | `symbol`, `limit?` |

### 거래 (5개)
| 도구명 | 설명 | 핵심 파라미터 |
|--------|------|--------------|
| `place_order` | 주문 생성 (2단계 확인) | `symbol`, `side`, `type`, `quantity`, `price?` |
| `cancel_order` | 주문 취소 | `symbol`, `order_id` |
| `cancel_all_orders` | 심볼 전체 주문 취소 | `symbol` |
| `view_open_orders` | 열린 주문 목록 | `symbol?` |
| `modify_order` | 주문 수정 | `symbol`, `order_id`, `quantity?`, `price?` |

### 리스크 관리 (6개)
| 도구명 | 설명 | 핵심 파라미터 |
|--------|------|--------------|
| `set_stop_loss` | 스탑로스 설정 | `symbol`, `stop_price` |
| `set_take_profit` | 익절 설정 | `symbol`, `take_price` |
| `auto_sl_tp` | 진입가 기준 자동 SL/TP | `symbol`, `sl_percent`, `tp_percent` |
| `set_trailing_stop` | 트레일링 스탑 | `symbol`, `callback_rate` |
| `change_leverage` | 레버리지 변경 | `symbol`, `leverage` |
| `change_margin_type` | 마진 타입 변경 | `symbol`, `margin_type` |

### 전략 (4개)
| 도구명 | 설명 | 핵심 파라미터 |
|--------|------|--------------|
| `list_strategies` | 저장된 전략 목록 | 없음 |
| `view_strategy` | 전략 상세 보기 | `name` |
| `create_strategy` | 새 전략 생성 | `name`, `symbol`, 규칙들 |
| `modify_strategy` | 전략 수정 | `name`, `updates` |

### 백테스트 (2개)
| 도구명 | 설명 | 핵심 파라미터 |
|--------|------|--------------|
| `run_backtest` | 전략 백테스트 실행 | `strategy_name`, `symbol`, `start_date`, `end_date` |
| `quick_backtest` | 최근 N일 빠른 백테스트 | `strategy_name`, `symbol`, `days?` |

## 안전장치 (5층)

1. **테스트넷 기본**: 시작 시 항상 testnet. live 전환은 명시적 확인 필요
2. **2단계 확인**: 주문/취소/레버리지 변경 시 confirm_token으로 재확인
3. **포지션 제한**: 심볼별 최대 포지션 사이즈 설정
4. **레이트 리밋**: X-MBX-USED-WEIGHT 헤더 추적, 한도 근접 시 자동 대기
5. **감사 로그**: 모든 도구 호출을 audit.jsonl에 기록

## 핵심 의존성

```toml
dependencies = [
    "mcp[cli]>=1.0.0",
    "httpx>=0.27",
    "pydantic>=2.0",
    "python-dotenv>=1.0",
    "pandas>=2.0",       # 백테스트용
    "numpy>=1.24",       # 수치 계산
]
```

## 구현 순서 (6단계)

1. **Phase 1**: `client.py` + `models.py` + `safety.py` — 바이낸스 API 연결, 서명, 기본 구조
2. **Phase 2**: `tools/account.py` + `tools/market.py` — 읽기 전용 도구 (테스트넷에서 검증)
3. **Phase 3**: `tools/trading.py` + `tools/risk.py` — 주문/리스크 도구 (확인 게이트 포함)
4. **Phase 4**: `tools/strategy.py` — 전략 JSON CRUD
5. **Phase 5**: `tools/backtest.py` + `backtest/engine.py` — 백테스트 엔진
6. **Phase 6**: Claude Code 등록, README, 에러 메시지 다듬기

## 사용 예시 (비개발자 관점)

```
사용자: "내 잔고 얼마야?"
→ check_balance 호출 → "USDT 잔고: 1,234.56, 사용 가능: 1,000.00, 미실현PnL: +34.56"

사용자: "이더 롱 0.1개 시장가로 잡아줘"
→ place_order(symbol="ETHUSDT", side="BUY", type="MARKET", quantity=0.1)
→ "⚠️ 확인: ETHUSDT 0.1개 시장가 매수 주문을 실행합니다. 확인하시겠습니까?"
→ 사용자 확인 후 실행

사용자: "지금 포지션에 2% 손절, 5% 익절 걸어줘"
→ auto_sl_tp(symbol="ETHUSDT", sl_percent=2.0, tp_percent=5.0)
→ 진입가 기준으로 자동 계산하여 STOP_MARKET + TAKE_PROFIT_MARKET 주문 설정
```

## 바이낸스 API 엔드포인트 매핑

| 기능 | 엔드포인트 | 메서드 |
|------|-----------|--------|
| 잔고 | GET /fapi/v3/balance | SIGNED |
| 계좌 정보 | GET /fapi/v3/account | SIGNED |
| 포지션 | GET /fapi/v2/positionRisk | SIGNED |
| 주문 생성 | POST /fapi/v1/order | SIGNED |
| 주문 취소 | DELETE /fapi/v1/order | SIGNED |
| 주문 수정 | PUT /fapi/v1/order | SIGNED |
| 열린 주문 | GET /fapi/v1/openOrders | SIGNED |
| 레버리지 | POST /fapi/v1/leverage | SIGNED |
| 마진타입 | POST /fapi/v1/marginType | SIGNED |
| 현재가 | GET /fapi/v1/ticker/price | PUBLIC |
| 24시간 | GET /fapi/v1/ticker/24hr | PUBLIC |
| 펀딩레이트 | GET /fapi/v1/fundingRate | PUBLIC |
| Kline | GET /fapi/v1/klines | PUBLIC |
| 수익내역 | GET /fapi/v1/income | SIGNED |
