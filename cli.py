#!/usr/bin/env python3
"""
cli.py — Command-Line Interface for the Binance Futures Trading Bot.

Usage examples
--------------
  # Market buy
  python cli.py place --symbol BTCUSDT --side BUY --type MARKET --qty 0.001

  # Limit sell
  python cli.py place --symbol ETHUSDT --side SELL --type LIMIT --qty 0.01 --price 3500

  # Stop-market (bonus)
  python cli.py place --symbol BTCUSDT --side SELL --type STOP_MARKET --qty 0.001 --stop-price 60000

  # Check account balance
  python cli.py account

  # List open orders
  python cli.py orders --symbol BTCUSDT
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
from typing import Optional

# ── Ensure project root is on the path (for `python cli.py` usage) ─────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.client     import BinanceFuturesClient, BinanceAPIError, BinanceNetworkError
from bot.logging_config import setup_logging, get_logger
from bot.orders     import place_order
from bot.validators import validate_order_params, ValidationError

# ── Banner ─────────────────────────────────────────────────────────────────

BANNER = r"""
  ╔══════════════════════════════════════════════════════╗
  ║       Binance Futures Testnet — Trading Bot          ║
  ║       USDT-M Perpetuals  |  Python 3.x               ║
  ╚══════════════════════════════════════════════════════╝
"""


# ── Environment helpers ────────────────────────────────────────────────────

def _get_credentials() -> tuple[str, str]:
    """
    Read API credentials from environment variables.

    Set them before running:
      export BINANCE_API_KEY="your_key"
      export BINANCE_API_SECRET="your_secret"

    Or pass --api-key / --api-secret on the command line.
    """
    key    = os.environ.get("BINANCE_API_KEY", "")
    secret = os.environ.get("BINANCE_API_SECRET", "")
    return key, secret


# ── Formatters ─────────────────────────────────────────────────────────────

def _fmt_request_summary(
    symbol:     str,
    side:       str,
    order_type: str,
    quantity:   str,
    price:      Optional[str],
    stop_price: Optional[str],
) -> str:
    lines = [
        "",
        "  ┌─── ORDER REQUEST ───────────────────────────────",
        f"  │  Symbol     : {symbol}",
        f"  │  Side       : {side}",
        f"  │  Order Type : {order_type}",
        f"  │  Quantity   : {quantity}",
    ]
    if price:
        lines.append(f"  │  Price      : {price}")
    if stop_price:
        lines.append(f"  │  Stop Price : {stop_price}")
    lines.append("  └────────────────────────────────────────────────")
    return "\n".join(lines)


# ── Sub-command handlers ───────────────────────────────────────────────────

def cmd_place(args: argparse.Namespace, client: BinanceFuturesClient, logger) -> int:
    """Handle the 'place' sub-command."""
    # --- Validate inputs ---
    try:
        validated = validate_order_params(
            symbol     = args.symbol,
            side       = args.side,
            order_type = args.type,
            quantity   = args.qty,
            price      = args.price,
            stop_price = args.stop_price,
        )
    except ValidationError as exc:
        logger.error("Validation failed: %s", exc)
        print(f"\n  ✗ Input Error: {exc}\n", file=sys.stderr)
        return 1

    # --- Print request summary ---
    print(_fmt_request_summary(
        symbol     = validated["symbol"],
        side       = validated["side"],
        order_type = validated["order_type"],
        quantity   = str(validated["quantity"]),
        price      = str(validated["price"])      if validated["price"]      else None,
        stop_price = str(validated["stop_price"]) if validated["stop_price"] else None,
    ))

    # --- Place order ---
    result = place_order(
        client        = client,
        symbol        = validated["symbol"],
        side          = validated["side"],
        order_type    = validated["order_type"],
        quantity      = validated["quantity"],
        price         = validated["price"],
        stop_price    = validated["stop_price"],
        time_in_force = args.tif,
    )

    # --- Print result ---
    print("\n  ── ORDER RESPONSE ──────────────────────────────")
    print(result.pretty())

    if result.success:
        print("\n  ✔  Order submitted successfully!\n")
        if args.json:
            print(json.dumps(result.raw, indent=2))
        return 0
    else:
        print(f"\n  ✗  Order failed: {result.error}\n", file=sys.stderr)
        return 1


def cmd_account(args: argparse.Namespace, client: BinanceFuturesClient, logger) -> int:
    """Handle the 'account' sub-command."""
    try:
        account = client.get_account()
    except (BinanceAPIError, BinanceNetworkError) as exc:
        logger.error("Failed to fetch account: %s", exc)
        print(f"\n  ✗ Error: {exc}\n", file=sys.stderr)
        return 1

    assets = [a for a in account.get("assets", []) if float(a.get("walletBalance", 0)) > 0]
    print("\n  ┌─── ACCOUNT SUMMARY ─────────────────────────────")
    print(f"  │  Can Trade   : {account.get('canTrade')}")
    print(f"  │  Total Balance (USDT) : {account.get('totalWalletBalance', 'N/A')}")
    print(f"  │  Unrealised PnL       : {account.get('totalUnrealizedProfit', 'N/A')}")
    print("  │")
    print("  │  Non-zero assets:")
    for a in assets:
        print(f"  │    {a['asset']:<8} wallet={a['walletBalance']:<16} available={a['availableBalance']}")
    print("  └────────────────────────────────────────────────────\n")

    if args.json:
        print(json.dumps(account, indent=2))
    return 0


def cmd_orders(args: argparse.Namespace, client: BinanceFuturesClient, logger) -> int:
    """Handle the 'orders' sub-command."""
    try:
        orders = client.get_open_orders(symbol=args.symbol)
    except (BinanceAPIError, BinanceNetworkError) as exc:
        logger.error("Failed to fetch orders: %s", exc)
        print(f"\n  ✗ Error: {exc}\n", file=sys.stderr)
        return 1

    if not orders:
        print("\n  ℹ  No open orders.\n")
        return 0

    print(f"\n  ┌─── OPEN ORDERS ({len(orders)}) ─────────────────────────────")
    for o in orders:
        print(
            f"  │  [{o['orderId']}] {o['symbol']} {o['side']} {o['type']}"
            f"  qty={o['origQty']}  price={o['price']}  status={o['status']}"
        )
    print("  └────────────────────────────────────────────────────\n")

    if args.json:
        print(json.dumps(orders, indent=2))
    return 0


# ── Argument parser ────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog        = "trading_bot",
        description = textwrap.dedent("""\
            Binance Futures Testnet — Trading Bot CLI
            -----------------------------------------
            Place market, limit, and stop-market orders on USDT-M Futures.
        """),
        formatter_class = argparse.RawDescriptionHelpFormatter,
        epilog = textwrap.dedent("""\
            Environment variables:
              BINANCE_API_KEY      Your testnet API key
              BINANCE_API_SECRET   Your testnet API secret

            Examples:
              python cli.py place --symbol BTCUSDT --side BUY --type MARKET --qty 0.001
              python cli.py place --symbol ETHUSDT --side SELL --type LIMIT --qty 0.01 --price 3000
              python cli.py place --symbol BTCUSDT --side SELL --type STOP_MARKET --qty 0.001 --stop-price 60000
              python cli.py account
              python cli.py orders --symbol BTCUSDT
        """),
    )

    # ── Global options ─────────────────────────────────────────────────────
    parser.add_argument("--api-key",    default="", help="Binance API key (overrides env var)")
    parser.add_argument("--api-secret", default="", help="Binance API secret (overrides env var)")
    parser.add_argument("--log-dir",    default="logs", help="Directory for log files (default: logs)")
    parser.add_argument("--debug",      action="store_true", help="Enable DEBUG-level console output")
    parser.add_argument("--json",       action="store_true", help="Also print raw JSON response")

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # ── place ──────────────────────────────────────────────────────────────
    p_place = sub.add_parser("place", help="Place a new futures order")
    p_place.add_argument("--symbol", required=True,  metavar="SYMBOL",
                         help="Trading pair, e.g. BTCUSDT")
    p_place.add_argument("--side",   required=True,  choices=["BUY", "SELL"],
                         help="Order side: BUY or SELL")
    p_place.add_argument("--type",   required=True,
                         choices=["MARKET", "LIMIT", "STOP_MARKET"],
                         help="Order type")
    p_place.add_argument("--qty",    required=True,  type=float, metavar="QUANTITY",
                         help="Order quantity (e.g. 0.001)")
    p_place.add_argument("--price",  type=float, default=None, metavar="PRICE",
                         help="Limit price (required for LIMIT orders)")
    p_place.add_argument("--stop-price", type=float, default=None, metavar="STOP_PRICE",
                         dest="stop_price",
                         help="Stop trigger price (required for STOP_MARKET)")
    p_place.add_argument("--tif",    default="GTC", choices=["GTC", "IOC", "FOK"],
                         help="Time-in-force for LIMIT orders (default: GTC)")

    # ── account ────────────────────────────────────────────────────────────
    sub.add_parser("account", help="Show account balance and trading status")

    # ── orders ─────────────────────────────────────────────────────────────
    p_orders = sub.add_parser("orders", help="List open orders")
    p_orders.add_argument("--symbol", default=None, metavar="SYMBOL",
                          help="Filter by trading pair (optional)")

    return parser


# ── Entry point ────────────────────────────────────────────────────────────

def main() -> None:
    print(BANNER)

    parser = build_parser()
    args   = parser.parse_args()

    # ── Logging setup ──────────────────────────────────────────────────────
    import logging
    logger = setup_logging(
        log_dir       = args.log_dir,
        console_level = logging.DEBUG if args.debug else logging.INFO,
    )
    logger.info("Trading bot started — command=%s", args.command)

    # ── Credentials ────────────────────────────────────────────────────────
    env_key, env_secret = _get_credentials()
    api_key    = args.api_key    or env_key
    api_secret = args.api_secret or env_secret

    if not api_key or not api_secret:
        print(
            "  ✗ Error: API credentials not found.\n"
            "  Set BINANCE_API_KEY and BINANCE_API_SECRET environment variables,\n"
            "  or pass --api-key / --api-secret on the command line.\n",
            file=sys.stderr,
        )
        sys.exit(1)

    # ── Build client ───────────────────────────────────────────────────────
    try:
        client = BinanceFuturesClient(api_key=api_key, api_secret=api_secret)
        client.ping()
        logger.debug("API ping successful.")
    except Exception as exc:
        logger.error("Failed to initialise client: %s", exc)
        print(f"\n  ✗ Cannot connect to Binance Futures Testnet: {exc}\n", file=sys.stderr)
        sys.exit(1)

    # ── Dispatch ───────────────────────────────────────────────────────────
    dispatch = {
        "place":   cmd_place,
        "account": cmd_account,
        "orders":  cmd_orders,
    }

    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    exit_code = handler(args, client, logger)
    logger.info("Trading bot exiting — code=%d", exit_code)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
