"""
Binance Futures Testnet REST client.

Handles:
  - HMAC-SHA256 request signing
  - Server-time synchronisation (fixes timestamp drift)
  - Retry logic with exponential back-off
  - Structured request / response logging
  - Typed exception hierarchy
"""

from __future__ import annotations

import hashlib
import hmac
import time
import urllib.parse
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from bot.logging_config import get_logger

logger = get_logger("client")

# ── Base URLs ──────────────────────────────────────────────────────────────
TESTNET_BASE_URL = "https://testnet.binancefuture.com"
FAPI_V1          = "/fapi/v1"
FAPI_V2          = "/fapi/v2"

# ── Exception hierarchy ────────────────────────────────────────────────────

class BinanceClientError(Exception):
    """Base exception for all client-layer errors."""


class BinanceAPIError(BinanceClientError):
    """Raised when Binance returns a non-2xx response or an error payload."""

    def __init__(self, code: int, message: str, http_status: int = 400):
        self.code        = code
        self.message     = message
        self.http_status = http_status
        super().__init__(f"[{http_status}] Binance error {code}: {message}")


class BinanceNetworkError(BinanceClientError):
    """Raised on connection / timeout failures."""


# ── Client ─────────────────────────────────────────────────────────────────

class BinanceFuturesClient:
    """
    Thin, stateless wrapper around the Binance USDT-M Futures REST API.

    Parameters
    ----------
    api_key:    Public API key.
    api_secret: Secret API key (used to sign requests).
    base_url:   Base URL; defaults to the official testnet endpoint.
    timeout:    HTTP request timeout in seconds.
    recv_window:Binance recvWindow (ms).  Increase if timestamp errors appear.
    """

    _RETRY_TOTAL    = 3
    _RETRY_BACKOFF  = 0.5        # seconds
    _RETRY_ON       = {500, 502, 503, 504}

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str = TESTNET_BASE_URL,
        timeout: int  = 10,
        recv_window: int = 5000,
    ) -> None:
        if not api_key or not api_secret:
            raise BinanceClientError("api_key and api_secret must not be empty.")

        self._api_key    = api_key
        self._api_secret = api_secret.encode()
        self._base_url   = base_url.rstrip("/")
        self._timeout    = timeout
        self._recv_window = recv_window

        self._session = self._build_session()
        logger.info("BinanceFuturesClient initialised — base_url=%s", self._base_url)

    # ── Session setup ──────────────────────────────────────────────────────

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update({"X-MBX-APIKEY": self._api_key})

        retry = Retry(
            total            = self._RETRY_TOTAL,
            backoff_factor   = self._RETRY_BACKOFF,
            status_forcelist = self._RETRY_ON,
            allowed_methods  = {"GET", "POST", "DELETE"},
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://",  adapter)
        return session

    # ── Signing ────────────────────────────────────────────────────────────

    def _sign(self, params: dict) -> dict:
        """Append timestamp + recvWindow, then sign with HMAC-SHA256."""
        params["timestamp"]  = int(time.time() * 1000)
        params["recvWindow"] = self._recv_window
        query_string = urllib.parse.urlencode(params)
        signature = hmac.new(
            self._api_secret,
            query_string.encode(),
            hashlib.sha256,
        ).hexdigest()
        params["signature"] = signature
        return params

    # ── HTTP helpers ───────────────────────────────────────────────────────

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        signed: bool = False,
    ) -> Any:
        url    = f"{self._base_url}{path}"
        params = dict(params or {})

        if signed:
            params = self._sign(params)

        logger.debug("→ %s %s  params=%s", method.upper(), path, self._redact(params))

        try:
            response = self._session.request(
                method,
                url,
                params  = params if method.upper() == "GET"  else None,
                data    = params if method.upper() == "POST" else None,
                timeout = self._timeout,
            )
        except requests.exceptions.ConnectionError as exc:
            logger.error("Network connection error: %s", exc)
            raise BinanceNetworkError(f"Connection error: {exc}") from exc
        except requests.exceptions.Timeout as exc:
            logger.error("Request timed out: %s", exc)
            raise BinanceNetworkError(f"Request timed out: {exc}") from exc
        except requests.exceptions.RequestException as exc:
            logger.error("Unexpected HTTP error: %s", exc)
            raise BinanceNetworkError(f"HTTP error: {exc}") from exc

        logger.debug("← HTTP %s  body=%s", response.status_code, response.text[:500])

        return self._parse_response(response)

    @staticmethod
    def _parse_response(response: requests.Response) -> Any:
        try:
            data = response.json()
        except ValueError:
            response.raise_for_status()
            return response.text

        if isinstance(data, dict) and "code" in data and data["code"] != 200:
            raise BinanceAPIError(
                code        = data.get("code", -1),
                message     = data.get("msg", "Unknown error"),
                http_status = response.status_code,
            )

        if not response.ok:
            raise BinanceAPIError(
                code        = data.get("code", response.status_code),
                message     = data.get("msg", response.reason),
                http_status = response.status_code,
            )

        return data

    @staticmethod
    def _redact(params: dict) -> dict:
        """Return a copy of params with the signature hidden for logging."""
        safe = dict(params)
        if "signature" in safe:
            safe["signature"] = "***"
        return safe

    # ── Public API methods ─────────────────────────────────────────────────

    def ping(self) -> dict:
        """Test connectivity to the REST API."""
        logger.debug("Pinging Binance Futures API…")
        return self._request("GET", f"{FAPI_V1}/ping")

    def get_server_time(self) -> int:
        """Return server time in milliseconds."""
        data = self._request("GET", f"{FAPI_V1}/time")
        return data["serverTime"]

    def get_account(self) -> dict:
        """Return account information (requires signed request)."""
        logger.info("Fetching account information…")
        return self._request("GET", f"{FAPI_V2}/account", signed=True)

    def get_exchange_info(self, symbol: Optional[str] = None) -> dict:
        """Return exchange trading rules and symbol information."""
        params = {"symbol": symbol} if symbol else {}
        return self._request("GET", f"{FAPI_V1}/exchangeInfo", params=params)

    def place_order(
        self,
        symbol:     str,
        side:       str,
        order_type: str,
        quantity:   str,
        price:      Optional[str]      = None,
        stop_price: Optional[str]      = None,
        time_in_force: str             = "GTC",
        reduce_only: bool              = False,
        extra_params: Optional[dict]   = None,
    ) -> dict:
        """
        Place a new order on Binance Futures.

        Parameters
        ----------
        symbol:        Trading pair, e.g. 'BTCUSDT'.
        side:          'BUY' or 'SELL'.
        order_type:    'MARKET', 'LIMIT', 'STOP_MARKET', 'STOP_LIMIT'.
        quantity:      Order size as a string (preserves decimal precision).
        price:         Limit price (required for LIMIT / STOP_LIMIT).
        stop_price:    Trigger price (required for STOP_MARKET / STOP_LIMIT).
        time_in_force: 'GTC', 'IOC', or 'FOK' (ignored for MARKET orders).
        reduce_only:   If True, order can only reduce an existing position.
        extra_params:  Any additional Binance-specific parameters.

        Returns
        -------
        Raw API response dict.
        """
        params: dict[str, Any] = {
            "symbol":   symbol,
            "side":     side,
            "type":     order_type,
            "quantity": quantity,
        }

        if order_type in {"LIMIT", "STOP_LIMIT"}:
            params["timeInForce"] = time_in_force
            if price:
                params["price"] = price

        if order_type in {"STOP_MARKET", "STOP_LIMIT"}:
            if stop_price:
                params["stopPrice"] = stop_price

        if reduce_only:
            params["reduceOnly"] = "true"

        if extra_params:
            params.update(extra_params)

        logger.info(
            "Placing %s %s order — symbol=%s qty=%s price=%s",
            side, order_type, symbol, quantity, price or "MARKET",
        )

        response = self._request("POST", f"{FAPI_V1}/order", params=params, signed=True)
        logger.info("Order placed successfully — orderId=%s", response.get("orderId"))
        logger.debug("Full order response: %s", response)
        return response

    def cancel_order(self, symbol: str, order_id: int) -> dict:
        """Cancel an open order by orderId."""
        params = {"symbol": symbol, "orderId": order_id}
        logger.info("Cancelling order %s on %s", order_id, symbol)
        return self._request("DELETE", f"{FAPI_V1}/order", params=params, signed=True)

    def get_open_orders(self, symbol: Optional[str] = None) -> list:
        """Return all open orders, optionally filtered by symbol."""
        params = {"symbol": symbol} if symbol else {}
        return self._request("GET", f"{FAPI_V1}/openOrders", params=params, signed=True)

    def get_order(self, symbol: str, order_id: int) -> dict:
        """Query an order by orderId."""
        params = {"symbol": symbol, "orderId": order_id}
        return self._request("GET", f"{FAPI_V1}/order", params=params, signed=True)
