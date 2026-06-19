from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

try:
    import pandas as pd
except ImportError:  # pragma: no cover - depends on local setup
    pd = None

try:
    import MetaTrader5 as mt5
except ImportError:  # pragma: no cover - depends on local MT5 install
    mt5 = None


TIMEFRAMES = {
    "M1": 1,
    "M3": 3,
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 60,
    "H4": 240,
    "D1": 1440,
}


@dataclass
class MT5Result:
    ok: bool
    message: str
    data: Any = None


class MT5Service:
    """Small MT5 adapter inspired by OpenAlgo's broker boundary."""

    def __init__(self) -> None:
        self._connected = False
        self._login: str | None = None
        self._password: str | None = None
        self._server: str | None = None

    @property
    def available(self) -> bool:
        return mt5 is not None

    def connect(
        self,
        login: str | int | None = None,
        password: str | None = None,
        server: str | None = None,
    ) -> MT5Result:
        if mt5 is None:
            return MT5Result(False, "MetaTrader5 package is not installed")

        # Always shut down first so we don't reuse a stale session from
        # a previously logged-in account.
        if mt5.terminal_info() is not None:
            mt5.shutdown()
            self._connected = False

        path = os.getenv("MT5_PATH") or None
        initialized = mt5.initialize(path=path) if path else mt5.initialize()
        if not initialized:
            return MT5Result(False, self._last_error("MT5 initialize failed"))

        login = login or os.getenv("MT5_LOGIN")
        password = password or os.getenv("MT5_PASSWORD")
        server = server or os.getenv("MT5_SERVER")

        if login and password and server:
            try:
                login_number = int(login)
            except (TypeError, ValueError):
                mt5.shutdown()
                self._connected = False
                return MT5Result(False, "MT5 login must be a number")

            authorized = mt5.login(login_number, password=str(password), server=str(server))
            if not authorized:
                mt5.shutdown()
                self._connected = False
                return MT5Result(False, self._last_error("MT5 login failed"))

            # Save credentials so _ensure_ready() can restore this session if needed.
            self._login = str(login)
            self._password = str(password)
            self._server = str(server)
        else:
            # No explicit credentials — piggyback on the terminal's active session.
            # Clear stored creds so _ensure_ready() also uses the active session.
            self._login = None
            self._password = None
            self._server = None

        self._connected = True
        return MT5Result(True, "Connected to MT5", self.account_info())

    def disconnect(self) -> MT5Result:
        if mt5 is None:
            return MT5Result(False, "MetaTrader5 package is not installed")

        try:
            mt5.shutdown()
        finally:
            self._connected = False

        return MT5Result(True, "Disconnected from MT5")

    def status(self) -> dict[str, Any]:
        connected = mt5 is not None and mt5.terminal_info() is not None
        return {
            "package_available": self.available,
            "connected": connected,
            "account": self.account_info() if connected else None,
            "terminal": self.terminal_info() if connected else None,
        }

    def account_info(self) -> dict[str, Any] | None:
        if mt5 is None:
            return None
        info = mt5.account_info()
        return info._asdict() if info else None

    def terminal_info(self) -> dict[str, Any] | None:
        if mt5 is None:
            return None
        info = mt5.terminal_info()
        return info._asdict() if info else None

    def symbol_tick(self, symbol: str) -> MT5Result:
        symbol = symbol.strip().upper()
        ready = self._ensure_ready(symbol)
        if not ready.ok:
            return ready
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return MT5Result(False, self._last_error(f"No tick for {symbol}"))
        data = tick._asdict()
        data["time_iso"] = datetime.fromtimestamp(data["time"], timezone.utc).isoformat()
        return MT5Result(True, "Tick received", data)

    def candles(self, symbol: str, timeframe: str = "M1", bars: int = 120) -> MT5Result:
        if pd is None:
            return MT5Result(False, "pandas package is not installed")

        symbol = symbol.strip().upper()
        timeframe = timeframe.strip().upper()

        ready = self._ensure_ready(symbol)
        if not ready.ok:
            return ready

        tf = self._timeframe_value(timeframe)
        if tf is None:
            return MT5Result(False, f"Unsupported timeframe: {timeframe}")

        rates = mt5.copy_rates_from_pos(symbol, tf, 0, max(10, min(int(bars), 1000)))
        if rates is None:
            return MT5Result(False, self._last_error(f"No candles for {symbol}"))

        df = pd.DataFrame(rates)
        if df.empty:
            return MT5Result(False, f"No candle data returned for {symbol}")
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True).dt.strftime("%Y-%m-%d %H:%M:%S")
        return MT5Result(True, "Candles received", df.to_dict("records"))

    def positions(self, symbol: str | None = None) -> MT5Result:
        if mt5 is None:
            return MT5Result(False, "MetaTrader5 package is not installed")
        symbol = symbol.strip().upper() if symbol else None
        positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
        if positions is None:
            return MT5Result(False, self._last_error("Could not read positions"))
        return MT5Result(True, "Positions received", [p._asdict() for p in positions])

    def orders(self) -> MT5Result:
        if mt5 is None:
            return MT5Result(False, "MetaTrader5 package is not installed")
        orders = mt5.orders_get()
        if orders is None:
            return MT5Result(False, self._last_error("Could not read orders"))
        return MT5Result(True, "Orders received", [o._asdict() for o in orders])

    def market_order(
        self,
        symbol: str,
        side: str,
        volume: float,
        deviation: int = 20,
        magic: int = 240615,
        comment: str = "algo_system",
    ) -> MT5Result:
        symbol = symbol.strip().upper()
        side = side.upper()
        if not symbol:
            return MT5Result(False, "Symbol is required")
        if side not in {"BUY", "SELL"}:
            return MT5Result(False, "Side must be BUY or SELL")
        if volume <= 0:
            return MT5Result(False, "Volume must be greater than zero")

        ready = self._ensure_ready(symbol)
        if not ready.ok:
            return ready

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return MT5Result(False, self._last_error(f"No tick for {symbol}"))

        order_type = mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL
        price = tick.ask if side == "BUY" else tick.bid
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(volume),
            "type": order_type,
            "price": price,
            "deviation": int(deviation),
            "magic": magic,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        if result is None:
            return MT5Result(False, self._last_error("order_send failed"))
        result_dict = result._asdict()
        ok = result.retcode == mt5.TRADE_RETCODE_DONE
        return MT5Result(ok, result.comment or ("Order placed" if ok else "Order rejected"), result_dict)

    def close_position(self, ticket: int, deviation: int = 20) -> MT5Result:
        if mt5 is None:
            return MT5Result(False, "MetaTrader5 package is not installed")
        positions = mt5.positions_get(ticket=int(ticket))
        if not positions:
            return MT5Result(False, f"Position not found: {ticket}")

        position = positions[0]
        side = "SELL" if position.type == mt5.POSITION_TYPE_BUY else "BUY"
        tick = mt5.symbol_info_tick(position.symbol)
        if tick is None:
            return MT5Result(False, self._last_error(f"No tick for {position.symbol}"))
        price = tick.bid if side == "SELL" else tick.ask
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": int(ticket),
            "symbol": position.symbol,
            "volume": position.volume,
            "type": mt5.ORDER_TYPE_SELL if side == "SELL" else mt5.ORDER_TYPE_BUY,
            "price": price,
            "deviation": int(deviation),
            "magic": 240615,
            "comment": "algo_system close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        if result is None:
            return MT5Result(False, self._last_error("close order failed"))
        result_dict = result._asdict()
        ok = result.retcode == mt5.TRADE_RETCODE_DONE
        return MT5Result(ok, result.comment or ("Position closed" if ok else "Close rejected"), result_dict)

    def _ensure_ready(self, symbol: str) -> MT5Result:
        if mt5 is None:
            return MT5Result(False, "MetaTrader5 package is not installed")
        if not symbol:
            return MT5Result(False, "Symbol is required")
        if mt5.terminal_info() is None:
            # Re-connect using the credentials from the last successful login,
            # not from .env (which may point to a different account).
            connected = self.connect(
                login=self._login,
                password=self._password,
                server=self._server,
            )
            if not connected.ok:
                return connected
        if not mt5.symbol_select(symbol, True):
            return MT5Result(False, self._last_error(f"Could not select symbol {symbol}"))
        return MT5Result(True, "Ready")

    def _timeframe_value(self, timeframe: str) -> int | None:
        if mt5 is None:
            return None
        attr = f"TIMEFRAME_{timeframe.upper()}"
        return getattr(mt5, attr, None)

    def _last_error(self, fallback: str) -> str:
        if mt5 is None:
            return fallback
        code, message = mt5.last_error()
        return f"{fallback}: {code} {message}"
