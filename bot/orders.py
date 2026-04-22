"""
Order placement logic — bridges the validated CLI input to the API client.

Each function:
  1. Accepts already-validated parameters.
  2. Delegates to BinanceFuturesClient.
  3. Returns a normalised OrderResult.
  4. Logs every significant event.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Optional

from bot.client import BinanceFuturesClient, BinanceAPIError, BinanceNetworkError
from bot.logging_config import get_logger

logger = get_logger("orders")


# ── Result dataclass ───────────────────────────────────────────────────────

@dataclass
class OrderResult:
    """Normalised, human-readable representation of a placed order."""

    success:       bool
    order_id:      Optional[int]   = None
    symbol:        Optional[str]   = None
    side:          Optional[str]   = None
    order_type:    Optional[str]   = None
    status:        Optional[str]   = None
    orig_qty:      Optional[str]   = None
    executed_qty:  Optional[str]   = None
    avg_price:     Optional[str]   = None
    price:         Optional[str]   = None
    time_in_force: Optional[str]   = None
    raw:           dict            = field(default_factory=dict)
    error:         Optional[str]   = None

    def pretty(self) -> str:
        """Return a multi-line, human-readable summary."""
        if not self.success:
            return f"  ✗ Order FAILED: {self.error}"

        lines = [
            "  ┌─────────────────────────────────────────",
            f"  │  Order ID      : {self.order_id}",
            f"  │  Symbol        : {self.symbol}",
            f"  │  Side          : {self.side}",
            f"  │  Type          : {self.order_type}",
            f"  │  Status        : {self.status}",
            f"  │  Orig Qty      : {self.orig_qty}",
            f"  │  Executed Qty  : {self.executed_qty}",
            f"  │  Avg Fill Price: {self.avg_price or 'N/A'}",
        ]
        if self.price and self.price != "0":
            lines.append(f"  │  Limit Price   : {self.price}")
        if self.time_in_force:
            lines.append(f"  │  Time In Force : {self.time_in_force}")
        lines.append("  └─────────────────────────────────────────")
        return "\n".join(lines)


# ── Mapper ─────────────────────────────────────────────────────────────────

def _map_response(raw: dict) -> OrderResult:
    """Convert a raw Binance API order response to an OrderResult."""
    avg = raw.get("avgPrice", "0")
    return OrderResult(
        success       = True,
        order_id      = raw.get("orderId"),
        symbol        = raw.get("symbol"),
        side          = raw.get("side"),
        order_type    = raw.get("type"),
        status        = raw.get("status"),
        orig_qty      = raw.get("origQty"),
        executed_qty  = raw.get("executedQty"),
        avg_price     = avg if avg not in ("0", "0.00000000") else None,
        price         = raw.get("price"),
        time_in_force = raw.get("timeInForce"),
        raw           = raw,
    )


# ── Order placement functions ──────────────────────────────────────────────

def place_market_order(
    client:   BinanceFuturesClient,
    symbol:   str,
    side:     str,
    quantity: Decimal,
) -> OrderResult:
    """
    Place a MARKET order.

    Args:
        client:   Authenticated BinanceFuturesClient.
        symbol:   e.g. 'BTCUSDT'.
        side:     'BUY' or 'SELL'.
        quantity: Order size.

    Returns:
        OrderResult with success/failure information.
    """
    logger.info("── MARKET ORDER ── %s %s qty=%s", side, symbol, quantity)
    try:
        raw = client.place_order(
            symbol     = symbol,
            side       = side,
            order_type = "MARKET",
            quantity   = str(quantity),
        )
        result = _map_response(raw)
        logger.info(
            "MARKET order filled — orderId=%s executedQty=%s avgPrice=%s",
            result.order_id, result.executed_qty, result.avg_price,
        )
        return result

    except (BinanceAPIError, BinanceNetworkError) as exc:
        logger.error("MARKET order failed: %s", exc)
        return OrderResult(success=False, error=str(exc))


def place_limit_order(
    client:        BinanceFuturesClient,
    symbol:        str,
    side:          str,
    quantity:      Decimal,
    price:         Decimal,
    time_in_force: str = "GTC",
) -> OrderResult:
    """
    Place a LIMIT order.

    Args:
        client:        Authenticated BinanceFuturesClient.
        symbol:        e.g. 'BTCUSDT'.
        side:          'BUY' or 'SELL'.
        quantity:      Order size.
        price:         Limit price.
        time_in_force: 'GTC' (default), 'IOC', or 'FOK'.

    Returns:
        OrderResult with success/failure information.
    """
    logger.info(
        "── LIMIT ORDER ── %s %s qty=%s price=%s TIF=%s",
        side, symbol, quantity, price, time_in_force,
    )
    try:
        raw = client.place_order(
            symbol        = symbol,
            side          = side,
            order_type    = "LIMIT",
            quantity      = str(quantity),
            price         = str(price),
            time_in_force = time_in_force,
        )
        result = _map_response(raw)
        logger.info(
            "LIMIT order accepted — orderId=%s status=%s",
            result.order_id, result.status,
        )
        return result

    except (BinanceAPIError, BinanceNetworkError) as exc:
        logger.error("LIMIT order failed: %s", exc)
        return OrderResult(success=False, error=str(exc))


def place_stop_market_order(
    client:     BinanceFuturesClient,
    symbol:     str,
    side:       str,
    quantity:   Decimal,
    stop_price: Decimal,
) -> OrderResult:
    """
    Place a STOP_MARKET order (bonus: third order type).

    Triggers a market order when `stop_price` is reached.

    Args:
        client:     Authenticated BinanceFuturesClient.
        symbol:     Trading pair.
        side:       'BUY' or 'SELL'.
        quantity:   Order size.
        stop_price: Trigger price.

    Returns:
        OrderResult with success/failure information.
    """
    logger.info(
        "── STOP-MARKET ORDER ── %s %s qty=%s stopPrice=%s",
        side, symbol, quantity, stop_price,
    )
    try:
        raw = client.place_order(
            symbol     = symbol,
            side       = side,
            order_type = "STOP_MARKET",
            quantity   = str(quantity),
            stop_price = str(stop_price),
        )
        result = _map_response(raw)
        logger.info(
            "STOP_MARKET order accepted — orderId=%s status=%s",
            result.order_id, result.status,
        )
        return result

    except (BinanceAPIError, BinanceNetworkError) as exc:
        logger.error("STOP_MARKET order failed: %s", exc)
        return OrderResult(success=False, error=str(exc))


# ── Dispatch helper ────────────────────────────────────────────────────────

def place_order(
    client:        BinanceFuturesClient,
    symbol:        str,
    side:          str,
    order_type:    str,
    quantity:      Decimal,
    price:         Optional[Decimal] = None,
    stop_price:    Optional[Decimal] = None,
    time_in_force: str               = "GTC",
) -> OrderResult:
    """
    Unified dispatch function — routes to the correct order placement handler.

    Args:
        client:        Authenticated BinanceFuturesClient.
        symbol:        Trading pair.
        side:          'BUY' or 'SELL'.
        order_type:    'MARKET', 'LIMIT', or 'STOP_MARKET'.
        quantity:      Order size.
        price:         Limit price (required for LIMIT).
        stop_price:    Stop trigger price (required for STOP_MARKET / STOP_LIMIT).
        time_in_force: For LIMIT orders.

    Returns:
        OrderResult instance.
    """
    handlers = {
        "MARKET":      lambda: place_market_order(client, symbol, side, quantity),
        "LIMIT":       lambda: place_limit_order(
                            client, symbol, side, quantity, price, time_in_force
                        ),
        "STOP_MARKET": lambda: place_stop_market_order(
                            client, symbol, side, quantity, stop_price
                        ),
    }

    handler = handlers.get(order_type)
    if handler is None:
        err = f"Unsupported order type: {order_type}"
        logger.error(err)
        return OrderResult(success=False, error=err)

    return handler()
