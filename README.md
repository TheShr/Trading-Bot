# Binance Futures Testnet Trading Bot

A professional-grade Python CLI application for placing orders on the Binance USDT-M Futures Testnet. Built with clean architecture, structured logging, robust error handling, and a fully documented command-line interface.

---

## Features

- **Order Types:** `MARKET`, `LIMIT`, `STOP_MARKET`
- **Sides:** `BUY` and `SELL`
- **CLI:** `argparse`-based with `--help` on every subcommand
- **Validation:** Independent validation for symbol, side, type, quantity, price, and stop price
- **Logging:** Rotating file logger with coloured console output; DEBUG/INFO independently configurable
- **Error Handling:** Typed exceptions — `BinanceAPIError`, `BinanceNetworkError`, `ValidationError`
- **Architecture:** Clean separation across client, orders, validators, and logging layers

---

## Project Structure

```
trading_bot/
├── bot/
│   ├── __init__.py          # Package marker
│   ├── client.py            # Binance REST client (signing, retries, parsing)
│   ├── orders.py            # Order placement logic + OrderResult dataclass
│   ├── validators.py        # All input validation (raises ValidationError)
│   └── logging_config.py   # Dual-channel rotating logger with coloured console
├── cli.py                   # CLI entry point (argparse subcommands)
├── logs/
│   ├── market_order_example.log
│   └── limit_order_example.log
├── requirements.txt
└── README.md
```

---

## Setup

### Prerequisites

- Python 3.8 or higher
- A [Binance Futures Testnet](https://testnet.binancefuture.com) account

### 1. Get Testnet API Credentials

1. Register at [https://testnet.binancefuture.com](https://testnet.binancefuture.com)
2. Log in, click your avatar, and navigate to **API Key**
3. Generate a new key pair and save both the **API Key** and **Secret Key**

### 2. Install Dependencies

```bash
cd trading_bot
pip install -r requirements.txt
```

### 3. Set Credentials

**Recommended — environment variables (never hardcode secrets):**

```bash
# Linux / macOS
export BINANCE_API_KEY="your_api_key_here"
export BINANCE_API_SECRET="your_secret_key_here"

# Windows PowerShell
$env:BINANCE_API_KEY="your_api_key_here"
$env:BINANCE_API_SECRET="your_secret_key_here"
```

Alternatively, pass credentials directly on the command line (less secure):

```bash
python cli.py --api-key YOUR_KEY --api-secret YOUR_SECRET place ...
```

---

## Usage

### Global Flags

These flags apply to all subcommands.

| Flag | Description |
|---|---|
| `--debug` | Show DEBUG-level output in the console |
| `--json` | Also print the raw JSON API response |
| `--log-dir PATH` | Custom log directory (default: `logs/`) |
| `--api-key` / `--api-secret` | Override environment variable credentials inline |

---

### `place` — Place an Order

```
python cli.py place --symbol SYMBOL --side BUY|SELL --type TYPE --qty QTY [--price P] [--stop-price SP] [--tif GTC|IOC|FOK]
```

#### MARKET Order

```bash
# Buy 0.001 BTC at market price
python cli.py place --symbol BTCUSDT --side BUY --type MARKET --qty 0.001

# Sell 0.01 ETH at market price
python cli.py place --symbol ETHUSDT --side SELL --type MARKET --qty 0.01
```

Example output:

```
╔══════════════════════════════════════════════════════╗
║     Binance Futures Testnet — Trading Bot            ║
╚══════════════════════════════════════════════════════╝

┌─── ORDER REQUEST ──────────────────────────────
│  Symbol      : BTCUSDT
│  Side        : BUY
│  Order Type  : MARKET
│  Quantity    : 0.001
└────────────────────────────────────────────────

── ORDER RESPONSE ───────────────────────────────
┌─────────────────────────────────────────
│  Order ID      : 4089893475
│  Symbol        : BTCUSDT
│  Side          : BUY
│  Type          : MARKET
│  Status        : FILLED
│  Orig Qty      : 0.001
│  Executed Qty  : 0.001
│  Avg Fill Price: 93412.50000
└─────────────────────────────────────────

Order submitted successfully.
```

#### LIMIT Order

```bash
# Limit-buy 0.001 BTC at $90,000
python cli.py place --symbol BTCUSDT --side BUY --type LIMIT --qty 0.001 --price 90000

# Limit-sell 0.05 ETH at $3,500 with IOC time-in-force
python cli.py place --symbol ETHUSDT --side SELL --type LIMIT --qty 0.05 --price 3500 --tif IOC
```

#### STOP_MARKET Order

```bash
# Trigger a market-sell if BTC drops to $60,000
python cli.py place --symbol BTCUSDT --side SELL --type STOP_MARKET --qty 0.001 --stop-price 60000

# Trigger a market-buy if BTC rises to $100,000
python cli.py place --symbol BTCUSDT --side BUY --type STOP_MARKET --qty 0.001 --stop-price 100000
```

---

### `account` — View Account Balance

```bash
python cli.py account

# Also dump raw JSON response
python cli.py account --json
```

---

### `orders` — List Open Orders

```bash
# List all open orders
python cli.py orders

# Filter by symbol
python cli.py orders --symbol BTCUSDT
```

---

### Full Help

```bash
python cli.py --help
python cli.py place --help
python cli.py account --help
python cli.py orders --help
```

---

## Logging

Logs are written to `logs/trading_bot.log` with rotation (max 5 MB per file, 5 backups retained).

| Channel | Default Level | Content |
|---|---|---|
| Console (coloured) | INFO | Human-readable status messages |
| File (plain text) | DEBUG | Full request params, responses, stack traces |

To enable DEBUG output in the console:

```bash
python cli.py --debug place --symbol BTCUSDT --side BUY --type MARKET --qty 0.001
```

Sample log files are available in `logs/market_order_example.log` and `logs/limit_order_example.log`.

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| Missing or invalid API credentials | Clear error message, exit code 1 |
| Invalid symbol, side, or type | `ValidationError` printed to stderr |
| Missing required price for LIMIT order | `ValidationError` raised before API call |
| Binance API error (e.g. insufficient balance) | `BinanceAPIError(code, message)` logged and displayed |
| Network timeout or connection refused | `BinanceNetworkError` with 3 retry attempts and exponential back-off |
| Unexpected JSON or server error | Caught, logged, and reported cleanly |

---

## Architecture

| Module | Responsibility |
|---|---|
| `bot/client.py` | Pure API layer: signs requests, handles HTTP, raises typed exceptions. No business logic. |
| `bot/orders.py` | Business logic: maps validated inputs to client calls, returns `OrderResult` dataclass. |
| `bot/validators.py` | All validation logic isolated here; raises `ValidationError` on invalid input. |
| `bot/logging_config.py` | Single source of truth for all logging; returns child loggers via `get_logger(name)`. |
| `cli.py` | Thin presentation layer: parses arguments, calls validators and orders, formats output. |

---

## Assumptions

1. **Testnet only** — the base URL is hardcoded to `https://testnet.binancefuture.com`. A `--base-url` override can be added trivially for production use.
2. **USDT-M Perpetuals** — only `/fapi/v1` (futures) endpoints are used.
3. **Position side** defaults to `BOTH` (one-way mode). Hedge mode is not implemented.
4. **Quantity precision** — the user is responsible for providing a quantity that meets the symbol's lot-size filter. The bot passes the value as-is to the API and surfaces any precision errors from Binance.

---

## Dependencies

```
requests>=2.31.0   # HTTP client with retry adapter
urllib3>=2.0.0     # Underlying HTTP library (retry support)
```

All other dependencies are from the Python standard library.

---


