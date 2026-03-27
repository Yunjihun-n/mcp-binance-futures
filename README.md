# Binance Futures MCP Server

Claude Code / Claude Desktop에서 자연어로 바이낸스 USDS-마진 선물 거래를 관리하는 MCP 서버.

개발을 모르는 사람도 "잔고 얼마야?", "비트코인 롱 잡아줘", "2% 손절 걸어" 같은 말로 선물 거래를 할 수 있습니다.

## 기능 (27개 도구)

| 카테고리 | 도구 | 설명 |
|---------|------|------|
| **계좌** | `check_balance`, `view_positions`, `account_summary`, `income_history` | 잔고, 포지션, 수익 내역 조회 |
| **시장** | `get_price`, `get_market_stats`, `get_funding_rate` | 현재가, 24시간 통계, 펀딩레이트 |
| **거래** | `place_order`, `cancel_order`, `cancel_all_orders`, `view_open_orders`, `modify_order` | 시장가/지정가 주문, 취소, 수정 |
| **리스크** | `set_stop_loss`, `set_take_profit`, `auto_sl_tp`, `set_trailing_stop`, `change_leverage`, `change_margin_type` | 손절/익절, 트레일링 스탑, 레버리지 |
| **전략** | `list_strategies`, `view_strategy`, `create_strategy`, `modify_strategy`, `delete_strategy` | 전략 생성/수정/삭제 |
| **백테스트** | `run_backtest`, `quick_backtest`, `backtest_data_guide` | 과거 데이터로 전략 테스트 |
| **설정** | `switch_mode` | 테스트넷/실거래 전환 |

## 안전장치

- **테스트넷 기본**: 시작 시 항상 테스트넷. 실거래 전환은 2단계 확인 필요
- **2단계 확인**: 주문, 취소, 레버리지 변경 등 위험한 작업은 확인 토큰으로 재확인
- **감사 로그**: 모든 도구 호출을 `audit.jsonl`에 기록

## 설치

### 1. 코드 다운로드

```bash
git clone https://github.com/younjihoon/mcp-binance-futures.git
cd mcp-binance-futures
```

### 2. 의존성 설치

```bash
# Poetry 사용
poetry install

# 또는 pip 사용
pip install -e .
```

### 3. 바이낸스 API 키 발급

1. [바이낸스](https://www.binance.com/) 계정 생성 및 로그인
2. API Management에서 API 키 생성
3. **선물 거래 권한** 활성화
4. (선택) [테스트넷](https://testnet.binancefuture.com/)에서 테스트용 키 발급

### 4. Claude Code에 MCP 등록

프로젝트 루트에 `.mcp.json` 파일 생성:

```json
{
  "mcpServers": {
    "binance-futures": {
      "command": "poetry",
      "args": ["--directory", "/path/to/mcp-binance-futures", "run", "mcp-binance-futures"],
      "env": {
        "BINANCE_TESTNET_API_KEY": "여기에_테스트넷_API키",
        "BINANCE_TESTNET_SECRET_KEY": "여기에_테스트넷_시크릿키",
        "BINANCE_LIVE_API_KEY": "여기에_실거래_API키",
        "BINANCE_LIVE_SECRET_KEY": "여기에_실거래_시크릿키"
      }
    }
  }
}
```

> `/path/to/mcp-binance-futures`를 실제 설치 경로로 변경하세요.
> 테스트넷만 사용할 경우 LIVE 키는 비워두어도 됩니다.

### 5. Claude Code 재시작

MCP 서버가 자동으로 연결됩니다.

## 사용 예시

```
"내 잔고 얼마야?"
"비트코인 현재가"
"이더 0.1개 롱 시장가로 잡아줘"
"지금 포지션에 2% 손절 5% 익절 걸어"
"레버리지 10배로 변경"
"eth_scalp 전략 만들어줘 - ETHUSDT 롱 0.05개, 손절 1.5%, 익절 3%"
"그 전략으로 최근 7일 백테스트"
```

## 멀티 심볼 지원

BTCUSDT, ETHUSDT, SOLUSDT 등 바이낸스 USDS-마진 선물의 모든 심볼을 지원합니다.

## 요구 사항

- Python >= 3.11
- Poetry (권장) 또는 pip
- 바이낸스 선물 계정 + API 키
- Claude Code 또는 Claude Desktop

## 라이선스

MIT
