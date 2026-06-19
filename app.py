from __future__ import annotations

import atexit
import os
import importlib.util
import traceback
from pathlib import Path

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from mt5_service import MT5Service
from strategies.ema_crossover import EMACrossoverStrategy
from strategy_runner import StrategyRunner
import trading_store


try:
    from dotenv import load_dotenv
    DOTENV_IMPORT_ERROR = None
except ImportError as exc:  # pragma: no cover - depends on local setup
    DOTENV_IMPORT_ERROR = exc

    def load_dotenv(*_args, **_kwargs):
        return False

    
@atexit.register
def shutdown_everything():
    try:
        strategy_runner.stop()
    except Exception:
        pass

    try:
        mt5_service.disconnect()
    except Exception:
        pass
    
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

app = Flask(__name__)
mt5_service = MT5Service()
strategy_runner = StrategyRunner(mt5_service)
startup_connection = mt5_service.connect()


def api_response(ok: bool, message: str, data=None, status: int = 200):
    return jsonify({"ok": ok, "message": message, "data": data}), status


def log_report(message: str) -> None:
    strategy_runner.log(message)


def dependency_reports() -> list[str]:
    checks = {
        "python-dotenv": "dotenv",
        "pandas": "pandas",
        "MetaTrader5": "MetaTrader5",
    }
    if trading_store.using_postgres():
        checks["psycopg"] = "psycopg"
    reports = []
    for package, module in checks.items():
        if importlib.util.find_spec(module) is None:
            reports.append(f"Missing dependency: {package}. Run pip install -r requirements.txt")
    return reports


def safe_int(value, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def safe_float(value, default: float, minimum: float | None = None) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    if minimum is not None:
        parsed = max(minimum, parsed)
    return parsed


def json_payload() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        log_report(f"Invalid JSON payload on {request.path}; using defaults")
        return {}
    return payload


for report in dependency_reports():
    log_report(report)

log_report(startup_connection.message)

try:
    trading_store.init_db()
    log_report(f"Database ready: {trading_store.database_label()}")
except Exception as exc:  # pragma: no cover - depends on local database setup
    log_report(f"Database init failed: {exc}")


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    if isinstance(error, HTTPException):
        log_report(f"HTTP error on {request.path}: {error.description}")
        return api_response(False, error.description, status=error.code or 500)

    detail = "".join(traceback.format_exception_only(type(error), error)).strip()
    log_report(f"API error on {request.path}: {detail}")
    app.logger.exception("Unhandled API error")
    return api_response(False, "Internal server error. Check Logs for details.", status=500)


@app.get("/")
def index():
    return render_template(
        "index.html",
        default_symbol=os.getenv("DEFAULT_SYMBOL", "EURUSD"),
        default_volume=os.getenv("DEFAULT_VOLUME", "0.01"),
        default_timeframe=os.getenv("DEFAULT_TIMEFRAME", "M5"),
    )


@app.get("/api/status")
def status():
    return jsonify(
        {
            "mt5": mt5_service.status(),
            "strategy": strategy_runner.status(),
        }
    )


@app.post("/api/connect")
def connect():
    payload = json_payload()
    result = mt5_service.connect(
        login=str(payload.get("login", "")).strip() or None,
        password=str(payload.get("password", "")).strip() or None,
        server=str(payload.get("server", "")).strip() or None,
    )
    if not result.ok:
        log_report(f"Connect failed: {result.message}")
    return api_response(result.ok, result.message, result.data, 200 if result.ok else 400)


@app.post("/api/disconnect")
def disconnect():
    result = mt5_service.disconnect()
    if not result.ok:
        log_report(f"Disconnect failed: {result.message}")
    return api_response(result.ok, result.message, result.data, 200 if result.ok else 400)


@app.get("/api/tick/<symbol>")
def tick(symbol: str):
    result = mt5_service.symbol_tick(symbol.upper())
    if not result.ok:
        log_report(f"Tick request failed for {symbol.upper()}: {result.message}")
    return api_response(result.ok, result.message, result.data, 200 if result.ok else 400)


@app.get("/api/candles/<symbol>")
def candles(symbol: str):
    timeframe = request.args.get("timeframe", "M1")
    bars = safe_int(request.args.get("bars"), 120, minimum=10, maximum=1000)
    result = mt5_service.candles(symbol.upper(), timeframe, bars)
    if not result.ok:
        log_report(f"Candle request failed for {symbol.upper()} {timeframe}: {result.message}")
    return api_response(result.ok, result.message, result.data, 200 if result.ok else 400)


@app.get("/api/positions")
def positions():
    symbol = request.args.get("symbol") or None
    result = mt5_service.positions(symbol.upper() if symbol else None)
    if not result.ok:
        log_report(f"Positions request failed: {result.message}")
    return api_response(result.ok, result.message, result.data, 200 if result.ok else 400)


@app.get("/api/orders")
def orders():
    source = request.args.get("source", "history")
    if source == "mt5":
        result = mt5_service.orders()
        if not result.ok:
            log_report(f"MT5 order request failed: {result.message}")
        return api_response(result.ok, result.message, result.data, 200 if result.ok else 400)
    limit = safe_int(request.args.get("limit"), 100, minimum=1, maximum=500)
    return api_response(True, "Order history received", trading_store.list_orders(limit))


@app.get("/api/watchlist")
def watchlist():
    return api_response(True, "Watchlist received", trading_store.list_symbols())


@app.post("/api/watchlist")
def add_watch_symbol():
    payload = json_payload()
    symbol = str(payload.get("symbol", "")).strip().upper()
    timeframe = str(payload.get("timeframe", "M1")).strip().upper()
    if not symbol:
        return api_response(False, "Symbol is required", status=400)
    row = trading_store.add_symbol(symbol, timeframe)
    return api_response(True, "Symbol added", row)


@app.delete("/api/watchlist/<int:symbol_id>")
def delete_watch_symbol(symbol_id: int):
    if not trading_store.delete_symbol(symbol_id):
        return api_response(False, "Symbol not found", status=404)
    return api_response(True, "Symbol removed")


@app.get("/api/signals")
def signals():
    limit = safe_int(request.args.get("limit"), 100, minimum=1, maximum=500)
    return api_response(True, "Signals received", trading_store.list_signals(limit))


@app.post("/api/order")
def order():
    payload = json_payload()
    symbol = str(payload.get("symbol", "")).strip().upper()
    side = str(payload.get("side", "")).strip().upper()
    volume = safe_float(payload.get("volume"), 0.01, minimum=0.01)
    if not symbol:
        return api_response(False, "Symbol is required", status=400)
    if side not in {"BUY", "SELL"}:
        return api_response(False, "Side must be BUY or SELL", status=400)
    result = mt5_service.market_order(
        symbol=symbol,
        side=side,
        volume=volume,
    )
    if result.ok:
        trading_store.record_order(
            symbol=symbol,
            order_type=side,
            volume=volume,
            ticket=result.data.get("order") if isinstance(result.data, dict) else None,
            status=str(result.data.get("retcode")) if isinstance(result.data, dict) else "OK",
            comment=result.message,
        )
    if not result.ok:
        log_report(f"Order failed for {symbol} {side}: {result.message}")
    return api_response(result.ok, result.message, result.data, 200 if result.ok else 400)


@app.post("/api/positions/<int:ticket>/close")
def close_position(ticket: int):
    result = mt5_service.close_position(ticket)
    if not result.ok:
        log_report(f"Close position failed for {ticket}: {result.message}")
    return api_response(result.ok, result.message, result.data, 200 if result.ok else 400)


@app.post("/api/strategy/start")
def start_strategy():
    payload = json_payload()
    config = {
        "name": "EMA Crossover",
        "symbol": str(payload.get("symbol", os.getenv("DEFAULT_SYMBOL", "EURUSD"))).upper(),
        "timeframe": str(payload.get("timeframe", os.getenv("DEFAULT_TIMEFRAME", "M1"))).upper(),
        "volume": safe_float(payload.get("volume"), safe_float(os.getenv("DEFAULT_VOLUME"), 0.01, minimum=0.01), minimum=0.01),
        "fast_ema": safe_int(payload.get("fast_ema"), 9, minimum=1),
        "slow_ema": safe_int(payload.get("slow_ema"), 21, minimum=2),
        "poll_seconds": safe_int(payload.get("poll_seconds"), 10, minimum=1),
        "trade_enabled": bool(payload.get("trade_enabled", False)),
    }
    if not config["symbol"]:
        return api_response(False, "Symbol is required", status=400)
    if config["fast_ema"] >= config["slow_ema"]:
        return api_response(False, "Fast EMA must be lower than Slow EMA", status=400)
    config["signal_recorder"] = trading_store.record_signal
    config["order_recorder"] = trading_store.record_order
    ok, message = strategy_runner.start(EMACrossoverStrategy, config)
    if not ok:
        log_report(f"Strategy start failed: {message}")
    return api_response(ok, message, strategy_runner.status(), 200 if ok else 400)


@app.post("/api/strategy/stop")
def stop_strategy():
    ok, message = strategy_runner.stop()
    return api_response(ok, message, strategy_runner.status(), 200 if ok else 400)


if __name__ == "__main__":
    app.run(
        host=os.getenv("FLASK_HOST", "127.0.0.1"),
        port=safe_int(os.getenv("FLASK_PORT"), 5050, minimum=1, maximum=65535),
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
        use_reloader=False,
    )
