"""Binance USDS-Margined Futures REST API client (async)."""

import hmac
import hashlib
import time
from typing import Any
from urllib.parse import urlencode

import httpx

URLS = {
    "testnet": "https://demo-fapi.binance.com",
    "live": "https://fapi.binance.com",
}


class BinanceClient:
    """Async Binance Futures API client with HMAC-SHA256 signing."""

    def __init__(self, api_key: str, api_secret: str, mode: str = "testnet"):
        self.api_key = api_key
        self.api_secret = api_secret
        self.mode = mode
        self.base_url = URLS.get(mode, URLS["testnet"])
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"X-MBX-APIKEY": self.api_key},
                timeout=10.0,
            )
        return self._client

    def _sign(self, params: dict[str, Any]) -> dict[str, Any]:
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = 10000
        query = urlencode(params)
        signature = hmac.new(
            self.api_secret.encode(), query.encode(), hashlib.sha256
        ).hexdigest()
        params["signature"] = signature
        return params

    async def _request(
        self, method: str, path: str, params: dict | None = None, signed: bool = False
    ) -> dict | list:
        client = await self._get_client()
        params = params or {}
        # Remove None values
        params = {k: v for k, v in params.items() if v is not None}
        if signed:
            params = self._sign(params)

        try:
            resp = await client.request(method, path, params=params)
        except httpx.RequestError as e:
            raise BinanceAPIError(-1, f"네트워크 오류: {e}")

        # Check HTTP status first
        if resp.status_code >= 500:
            raise BinanceAPIError(resp.status_code, f"서버 오류 (HTTP {resp.status_code})")

        try:
            data = resp.json()
        except Exception:
            raise BinanceAPIError(resp.status_code, f"응답 파싱 실패 (HTTP {resp.status_code}): {resp.text[:200]}")

        # Binance API error format: {"code": -XXXX, "msg": "..."}
        if isinstance(data, dict) and "code" in data and int(data["code"]) < 0:
            raise BinanceAPIError(int(data["code"]), data.get("msg", "Unknown error"))

        if resp.status_code >= 400:
            msg = data.get("msg", resp.text[:200]) if isinstance(data, dict) else str(data)[:200]
            raise BinanceAPIError(resp.status_code, msg)

        return data

    # --- Public endpoints ---

    async def get_price(self, symbol: str) -> dict:
        return await self._request("GET", "/fapi/v1/ticker/price", {"symbol": symbol})

    async def get_ticker_24hr(self, symbol: str) -> dict:
        return await self._request("GET", "/fapi/v1/ticker/24hr", {"symbol": symbol})

    async def get_funding_rate(self, symbol: str, limit: int = 10) -> list:
        return await self._request(
            "GET", "/fapi/v1/fundingRate", {"symbol": symbol, "limit": limit}
        )

    async def get_klines(
        self, symbol: str, interval: str = "1h", limit: int = 500,
        start_time: int | None = None, end_time: int | None = None,
    ) -> list:
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        return await self._request("GET", "/fapi/v1/klines", params)

    async def get_exchange_info(self) -> dict:
        return await self._request("GET", "/fapi/v1/exchangeInfo")

    # --- Signed endpoints ---

    async def get_balance(self) -> list:
        return await self._request("GET", "/fapi/v3/balance", {}, signed=True)

    async def get_account(self) -> dict:
        return await self._request("GET", "/fapi/v3/account", {}, signed=True)

    async def get_position_risk(self, symbol: str | None = None) -> list:
        params = {}
        if symbol:
            params["symbol"] = symbol
        return await self._request("GET", "/fapi/v2/positionRisk", params, signed=True)

    async def get_open_orders(self, symbol: str | None = None) -> list:
        params = {}
        if symbol:
            params["symbol"] = symbol
        return await self._request("GET", "/fapi/v1/openOrders", params, signed=True)

    async def get_income(
        self, symbol: str | None = None, income_type: str | None = None, limit: int = 50
    ) -> list:
        params: dict[str, Any] = {"limit": limit}
        if symbol:
            params["symbol"] = symbol
        if income_type:
            params["incomeType"] = income_type
        return await self._request("GET", "/fapi/v1/income", params, signed=True)

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float | None = None,
        price: float | None = None,
        stop_price: float | None = None,
        close_position: bool = False,
        time_in_force: str | None = None,
        reduce_only: bool = False,
        callback_rate: float | None = None,
    ) -> dict:
        params: dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "type": order_type,
        }
        if quantity is not None:
            params["quantity"] = str(quantity)
        if price is not None:
            params["price"] = str(price)
        if stop_price is not None:
            params["stopPrice"] = str(stop_price)
        if close_position:
            params["closePosition"] = "true"
        if time_in_force:
            params["timeInForce"] = time_in_force
        if reduce_only:
            params["reduceOnly"] = "true"
        if callback_rate is not None:
            params["callbackRate"] = str(callback_rate)
        return await self._request("POST", "/fapi/v1/order", params, signed=True)

    async def cancel_order(self, symbol: str, order_id: int) -> dict:
        return await self._request(
            "DELETE", "/fapi/v1/order",
            {"symbol": symbol, "orderId": order_id}, signed=True,
        )

    async def cancel_all_orders(self, symbol: str) -> dict:
        return await self._request(
            "DELETE", "/fapi/v1/allOpenOrders",
            {"symbol": symbol}, signed=True,
        )

    async def modify_order(
        self, symbol: str, order_id: int,
        quantity: float | None = None, price: float | None = None,
    ) -> dict:
        params: dict[str, Any] = {"symbol": symbol, "orderId": order_id}
        if quantity is not None:
            params["quantity"] = str(quantity)
        if price is not None:
            params["price"] = str(price)
        return await self._request("PUT", "/fapi/v1/order", params, signed=True)

    async def change_leverage(self, symbol: str, leverage: int) -> dict:
        return await self._request(
            "POST", "/fapi/v1/leverage",
            {"symbol": symbol, "leverage": leverage}, signed=True,
        )

    async def change_margin_type(self, symbol: str, margin_type: str) -> dict:
        return await self._request(
            "POST", "/fapi/v1/marginType",
            {"symbol": symbol, "marginType": margin_type}, signed=True,
        )

    async def place_algo_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float | None = None,
        price: float | None = None,
        trigger_price: float | None = None,
        close_position: bool = False,
        reduce_only: bool = False,
        callback_rate: float | None = None,
    ) -> dict:
        """Place conditional algo order (STOP_MARKET, TAKE_PROFIT_MARKET, etc.)."""
        params: dict[str, Any] = {
            "algoType": "CONDITIONAL",
            "symbol": symbol,
            "side": side,
            "type": order_type,
        }
        if quantity is not None:
            params["quantity"] = str(quantity)
        if price is not None:
            params["price"] = str(price)
        if trigger_price is not None:
            params["triggerPrice"] = str(trigger_price)
        if close_position:
            params["closePosition"] = "true"
        if reduce_only:
            params["reduceOnly"] = "true"
        if callback_rate is not None:
            params["callbackRate"] = str(callback_rate)
        return await self._request("POST", "/fapi/v1/algoOrder", params, signed=True)

    async def cancel_algo_order(self, algo_id: int) -> dict:
        return await self._request(
            "DELETE", "/fapi/v1/algoOrder",
            {"algoId": algo_id}, signed=True,
        )

    async def get_open_algo_orders(self, symbol: str | None = None) -> list:
        params = {}
        if symbol:
            params["symbol"] = symbol
        result = await self._request("GET", "/fapi/v1/openAlgoOrders", params, signed=True)
        # API may return dict with "orders" key or list directly
        if isinstance(result, dict):
            return result.get("orders", [])
        return result

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()


class BinanceAPIError(Exception):
    def __init__(self, code: int, msg: str):
        self.code = code
        self.msg = msg
        super().__init__(f"Binance API Error [{code}]: {msg}")
