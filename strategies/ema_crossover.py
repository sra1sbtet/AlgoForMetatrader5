from __future__ import annotations

from typing import Any, Callable

try:
    import pandas as pd
except ImportError:  # pragma: no cover - depends on local setup
    pd = None


class EMACrossoverStrategy:
    def __init__(self, mt5_service, config: dict[str, Any], logger: Callable[[str], None]) -> None:
        self.mt5 = mt5_service
        self.config = config
        self.log = logger
        self.in_position = False
        self.last_candle_time = None
        self.disabled = False
        self.last_step_error = None

    def step(self) -> str | None:
        if self.disabled:
            return None

        if pd is None:
            self.log("pandas package is not installed")
            self.disabled = True
            return None

        symbol = self.config["symbol"]
        timeframe = self.config.get("timeframe", "M1")
        fast = int(self.config.get("fast_ema", 9))
        slow = int(self.config.get("slow_ema", 21))
        volume = float(self.config.get("volume", 0.01))
        trade_enabled = bool(self.config.get("trade_enabled", False))
        signal_recorder = self.config.get("signal_recorder")
        order_recorder = self.config.get("order_recorder")

        if fast >= slow:
            message = "Fast EMA must be lower than Slow EMA"
            if message != self.last_step_error:
                self.log(message)
                self.last_step_error = message
            return None

        result = self.mt5.candles(symbol, timeframe, max(80, slow + 5))
        if not result.ok:
            if result.message != self.last_step_error:
                self.log(result.message)
                self.last_step_error = result.message
            return None
        self.last_step_error = None

        data = pd.DataFrame(result.data)
        if data.empty or len(data) < slow + 2:
            self.log("Waiting for enough candles")
            return None

        data["fast"] = data["close"].ewm(span=fast, adjust=False).mean()
        data["slow"] = data["close"].ewm(span=slow, adjust=False).mean()

        previous = data.iloc[-3]
        last_closed = data.iloc[-2]
        candle_time = last_closed["time"]
        if candle_time == self.last_candle_time:
            return None
        self.last_candle_time = candle_time

        signal = None
        if previous["fast"] <= previous["slow"]: #and last_closed["fast"] > last_closed["slow"]:
            signal = "BUY"
        elif previous["fast"] >= previous["slow"]:# and last_closed["fast"] < last_closed["slow"]:
            signal = "SELL"

        self.log(
            f"{symbol} {timeframe} close={last_closed['close']:.5f} "
            f"ema{fast}={last_closed['fast']:.5f} ema{slow}={last_closed['slow']:.5f}"
        )

        if not signal:
            return None

        self.log(f"Signal: {signal}")
        if callable(signal_recorder):
            signal_recorder(symbol, timeframe, signal, float(last_closed["close"]))
        if trade_enabled:
            order = self.mt5.market_order(symbol, signal, volume, comment="algo_system ema")
            self.log(f"Order: {order.message}")
            if order.ok and callable(order_recorder):
                order_recorder(
                    symbol=symbol,
                    order_type=signal,
                    volume=volume,
                    ticket=order.data.get("order") if isinstance(order.data, dict) else None,
                    status=str(order.data.get("retcode")) if isinstance(order.data, dict) else "OK",
                    comment=order.message,
                )
        else:
            self.log("Paper mode: no live order sent")
        return signal
