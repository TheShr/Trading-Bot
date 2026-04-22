"""
Input validation for trading orders.
All validation logic is isolated here to keep other layers clean.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Optional

from bot.logging_config import get_logger

logger = get_logger("validators")

# ── Constants ──────────────────────────────────────────────────────────────

VALID_SIDES       = {"BUY", "SELL"}
VALID_ORDER_TYPES = {"MARKET", "LIMIT", "STOP_MARKET", "STOP_LIMIT"}

# Binance symbol pattern: all uppercase letters, 2–20 chars
SYMBOL_RE = re.compile(r"^[A-Z]{2,20}$")


# ── Custom exception ───────────────────────────────────────────────────────

class ValidationError(ValueError):
    """Raised when user-supplied order parameters fail validation."""


# ── Individual field validators ────────────────────────────────────────────

def validate_symbol(symbol: str) -> str:
    """Return the normalised symbol or raise ValidationError."""
    normalised = symbol.strip().upper()
    if not SYMBOL_RE.match(normalised):
        raise ValidationError(
            f"Invalid symbol '{symbol}'. "
            "Expected 2-20 uppercase letters (e.g. BTCUSDT)."
        )
    logger.debug("Symbol validated: %s", normalised)
    return normalised


def validate_side(side: str) -> str:
    """Return the normalised side (BUY/SELL) or raise ValidationError."""
    normalised = side.strip().upper()
    if normalised not in VALID_SIDES:
        raise ValidationError(
            f"Invalid side '{side}'. Must be one of: {', '.join(sorted(VALID_SIDES))}."
        )
    logger.debug("Side validated: %s", normalised)
    return normalised


def validate_order_type(order_type: str) -> str:
    """Return the normalised order type or raise ValidationError."""
    normalised = order_type.strip().upper()
    if normalised not in VALID_ORDER_TYPES:
        raise ValidationError(
            f"Invalid order type '{order_type}'. "
            f"Must be one of: {', '.join(sorted(VALID_ORDER_TYPES))}."
        )
    logger.debug("Order type validated: %s", normalised)
    return normalised


def validate_quantity(quantity: str | float) -> Decimal:
    """Parse and validate order quantity. Must be a positive number."""
    try:
        qty = Decimal(str(quantity))
    except InvalidOperation:
        raise ValidationError(f"Invalid quantity '{quantity}'. Must be a numeric value.")

    if qty <= 0:
        raise ValidationError(f"Quantity must be greater than zero, got {qty}.")

    logger.debug("Quantity validated: %s", qty)
    return qty


def validate_price(price: Optional[str | float], order_type: str) -> Optional[Decimal]:
    """
    Validate the price field.
    - Required for LIMIT and STOP_LIMIT orders.
    - Must be None / omitted for MARKET orders.
    """
    requires_price = order_type in {"LIMIT", "STOP_LIMIT"}

    if requires_price:
        if price is None:
            raise ValidationError(
                f"Price is required for {order_type} orders."
            )
        try:
            p = Decimal(str(price))
        except InvalidOperation:
            raise ValidationError(
                f"Invalid price '{price}'. Must be a numeric value."
            )
        if p <= 0:
            raise ValidationError(f"Price must be greater than zero, got {p}.")
        logger.debug("Price validated: %s", p)
        return p

    # MARKET order — price should not be provided
    if price is not None:
        logger.warning(
            "Price value '%s' was supplied for a MARKET order and will be ignored.", price
        )
    return None


def validate_stop_price(
    stop_price: Optional[str | float], order_type: str
) -> Optional[Decimal]:
    """Validate stop_price for STOP_MARKET / STOP_LIMIT orders."""
    requires_stop = order_type in {"STOP_MARKET", "STOP_LIMIT"}

    if requires_stop:
        if stop_price is None:
            raise ValidationError(
                f"stop_price is required for {order_type} orders."
            )
        try:
            sp = Decimal(str(stop_price))
        except InvalidOperation:
            raise ValidationError(
                f"Invalid stop_price '{stop_price}'. Must be a numeric value."
            )
        if sp <= 0:
            raise ValidationError(f"stop_price must be greater than zero, got {sp}.")
        logger.debug("Stop price validated: %s", sp)
        return sp

    return None


# ── Composite validator ────────────────────────────────────────────────────

def validate_order_params(
    symbol: str,
    side: str,
    order_type: str,
    quantity: str | float,
    price: Optional[str | float] = None,
    stop_price: Optional[str | float] = None,
) -> dict:
    """
    Validate all order parameters in one call.

    Returns:
        dict with normalised and parsed values ready for the API layer.

    Raises:
        ValidationError: on any invalid input.
    """
    logger.debug(
        "Validating order params — symbol=%s side=%s type=%s qty=%s price=%s stop=%s",
        symbol, side, order_type, quantity, price, stop_price,
    )

    validated = {
        "symbol":     validate_symbol(symbol),
        "side":       validate_side(side),
        "order_type": validate_order_type(order_type),
        "quantity":   validate_quantity(quantity),
        "price":      None,
        "stop_price": None,
    }

    # These depend on the normalised order_type
    validated["price"]      = validate_price(price, validated["order_type"])
    validated["stop_price"] = validate_stop_price(stop_price, validated["order_type"])

    logger.info(
        "Validation passed — %s %s %s qty=%s price=%s",
        validated["side"],
        validated["order_type"],
        validated["symbol"],
        validated["quantity"],
        validated["price"] or "N/A",
    )
    return validated
