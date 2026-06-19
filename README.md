# Algo System MT5 Terminal

A small Flask trading terminal for MetaTrader 5, built with the same broad idea as OpenAlgo's Python strategy hosting: keep broker calls behind a service, keep strategy execution separate from request handling, and expose simple JSON endpoints for the UI.

## What It Includes

- MT5 connect/disconnect and account status
- Live tick display
- Recent candle view
- Manual market buy/sell
- Position list and close-position action
- EMA crossover strategy runner
- Paper mode by default, with an explicit Live toggle

## Setup

```powershell
cd E:\algo_system_codex\algo_system_codex
copy .env.example .env
pip install -r requirements.txt
python app.py
```

Open:

```text
http://127.0.0.1:5050
```

## Dependencies

Install everything in `requirements.txt`.

- `Flask`: web server, dashboard routes, and JSON APIs
- `python-dotenv`: required for loading `.env` configuration
- `pandas`: required for candle transforms and EMA strategy calculations
- `MetaTrader5`: required for terminal connection, market data, positions, and orders
- `psycopg`: required when `DATABASE_URL` points to PostgreSQL

The app can show clear API messages when `pandas` is missing from candle or strategy calls, but it should still be installed for normal use.

## Database

SQLite is used when `DATABASE_URL` is blank. That is fine for quick local testing.

Use PostgreSQL for longer-running use, multiple app processes, remote hosting, backups, or when the strategy runner and dashboard may write at the same time.

Example `.env`:

```text
DATABASE_URL=postgresql://postgres:password@localhost:5432/algo_system
```

The app creates the `symbols`, `signals`, and `orders` tables automatically.

## MT5 Notes

You can either keep MetaTrader 5 open and logged in, or fill these values in `.env`:

```text
MT5_LOGIN=
MT5_PASSWORD=
MT5_SERVER=
MT5_PATH=
```

`MT5_PATH` is optional. Use it only when Python cannot find the installed terminal.

## Safety

The EMA strategy starts in paper mode. It logs BUY/SELL signals without placing orders until the `Live` toggle is enabled before starting the strategy.

This is a starter terminal, not a production risk engine. Add symbol validation, max daily loss, order confirmation, and account-level exposure checks before using it with real funds.
