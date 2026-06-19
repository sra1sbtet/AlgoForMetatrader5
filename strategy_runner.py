from __future__ import annotations

import threading
from datetime import datetime
from typing import Any


class StrategyRunner:
    """Runs one Python strategy loop in-process for a small terminal app."""

    def __init__(self, mt5_service) -> None:
        self.mt5 = mt5_service
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._state: dict[str, Any] = {
            "running": False,
            "name": None,
            "started_at": None,
            "last_signal": None,
            "last_error": None,
            "logs": [],
        }
        self._last_log_message: str | None = None

    def start(self, strategy_factory, config: dict[str, Any]) -> tuple[bool, str]:
        with self._lock:
            if self._state["running"]:
                return False, "Strategy is already running"
            self._stop.clear()
            strategy = strategy_factory(self.mt5, config, self.log)
            self._thread = threading.Thread(target=self._run, args=(strategy,), daemon=True)
            self._state.update(
                {
                    "running": True,
                    "name": config.get("name", "EMA Crossover"),
                    "started_at": datetime.now().isoformat(timespec="seconds"),
                    "last_signal": None,
                    "last_error": None,
                }
            )
            self._thread.start()
            self.log("Strategy started")
            return True, "Strategy started"

    def stop(self) -> tuple[bool, str]:
        with self._lock:
            if not self._state["running"]:
                return False, "No strategy is running"

            self._stop.set()

            thread = self._thread

        if thread and thread.is_alive():
            thread.join(timeout=10)
            if thread.is_alive():
                return False, "Strategy did not stop within 10 seconds"

        self.log("Strategy stopped")
        return True, "Strategy stopped"

    def status(self) -> dict[str, Any]:
        with self._lock:
            state = dict(self._state)
            state["logs"] = list(self._state.get("logs", []))
            return state

    def should_stop(self) -> bool:
        return self._stop.is_set()

    def log(self, message: str) -> None:
        if message == self._last_log_message:
            return
        self._last_log_message = message
        line = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "message": message,
        }
        with self._lock:
            logs = self._state.setdefault("logs", [])
            logs.append(line)
            del logs[:-250]

    def set_signal(self, signal: str | None) -> None:
        with self._lock:
            self._state["last_signal"] = signal

    def _run(self, strategy) -> None:
        try:
            while not self.should_stop():
                signal = strategy.step()
                self.set_signal(signal)
                interval = max(1, int(strategy.config.get("poll_seconds", 10)))
                self._stop.wait(interval)
        except Exception as exc:  # pragma: no cover - runtime protection
            with self._lock:
                self._state["last_error"] = str(exc)
            self.log(f"Strategy error: {exc}")
        finally:
            with self._lock:
                self._state["running"] = False
            self.log("Strategy stopped")
