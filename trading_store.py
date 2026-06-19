from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - depends on local setup
    psycopg = None
    dict_row = None


BASE_DIR = Path(__file__).resolve().parent
SQLITE_PATH = BASE_DIR / "database" / "trading.db"


def database_url() -> str:
    return os.getenv("DATABASE_URL", "").strip()


def using_postgres() -> bool:
    url = database_url().lower()
    return url.startswith("postgresql://") or url.startswith("postgres://")


def database_label() -> str:
    return "PostgreSQL" if using_postgres() else f"SQLite ({SQLITE_PATH})"


def get_connection():
    if using_postgres():
        if psycopg is None:
            raise RuntimeError("psycopg is required when DATABASE_URL uses PostgreSQL")
        return psycopg.connect(database_url(), row_factory=dict_row)

    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def param() -> str:
    return "%s" if using_postgres() else "?"


def rows_to_dicts(rows) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def init_db() -> None:
    if using_postgres():
        statements = [
            """
            CREATE TABLE IF NOT EXISTS symbols (
                id SERIAL PRIMARY KEY,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                UNIQUE(symbol, timeframe)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS signals (
                id SERIAL PRIMARY KEY,
                signal_time TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                signal TEXT NOT NULL,
                price DOUBLE PRECISION
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                order_time TEXT NOT NULL,
                symbol TEXT NOT NULL,
                order_type TEXT NOT NULL,
                volume DOUBLE PRECISION NOT NULL,
                ticket BIGINT,
                status TEXT,
                comment TEXT
            )
            """,
        ]
    else:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS symbols (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                UNIQUE(symbol, timeframe)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_time TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                signal TEXT NOT NULL,
                price REAL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_time TEXT NOT NULL,
                symbol TEXT NOT NULL,
                order_type TEXT NOT NULL,
                volume REAL NOT NULL,
                ticket INTEGER,
                status TEXT,
                comment TEXT
            )
            """,
        ]

    with get_connection() as conn:
        for statement in statements:
            conn.execute(statement)


def list_symbols(active_only: bool = True) -> list[dict[str, Any]]:
    marker = param()
    query = "SELECT * FROM symbols"
    params: tuple[Any, ...] = ()
    if active_only:
        query += f" WHERE active = {marker}"
        params = (1,)
    query += " ORDER BY symbol, timeframe"
    with get_connection() as conn:
        return rows_to_dicts(conn.execute(query, params).fetchall())


def add_symbol(symbol: str, timeframe: str) -> dict[str, Any]:
    marker = param()
    clean_symbol = symbol.strip().upper()
    clean_timeframe = timeframe.strip().upper()
    created_at = datetime.now().isoformat(timespec="seconds")

    with get_connection() as conn:
        if using_postgres():
            row = conn.execute(
                f"""
                INSERT INTO symbols (symbol, timeframe, active, created_at)
                VALUES ({marker}, {marker}, 1, {marker})
                ON CONFLICT(symbol, timeframe)
                DO UPDATE SET active = 1
                RETURNING *
                """,
                (clean_symbol, clean_timeframe, created_at),
            ).fetchone()
            return dict(row)

        conn.execute(
            f"""
            INSERT INTO symbols (symbol, timeframe, active, created_at)
            VALUES ({marker}, {marker}, 1, {marker})
            ON CONFLICT(symbol, timeframe) DO UPDATE SET active = 1
            """,
            (clean_symbol, clean_timeframe, created_at),
        )
        row = conn.execute(
            f"SELECT * FROM symbols WHERE symbol = {marker} AND timeframe = {marker}",
            (clean_symbol, clean_timeframe),
        ).fetchone()
        return dict(row)


def delete_symbol(symbol_id: int) -> bool:
    marker = param()
    with get_connection() as conn:
        cursor = conn.execute(f"DELETE FROM symbols WHERE id = {marker}", (int(symbol_id),))
        return cursor.rowcount > 0


def list_signals(limit: int = 100) -> list[dict[str, Any]]:
    marker = param()
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM signals ORDER BY id DESC LIMIT {marker}",
            (max(1, min(int(limit), 500)),),
        ).fetchall()
        return rows_to_dicts(rows)


def record_signal(symbol: str, timeframe: str, signal: str, price: float | None) -> None:
    marker = param()
    with get_connection() as conn:
        conn.execute(
            f"""
            INSERT INTO signals (signal_time, symbol, timeframe, signal, price)
            VALUES ({marker}, {marker}, {marker}, {marker}, {marker})
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                symbol.upper(),
                timeframe.upper(),
                signal.upper(),
                price,
            ),
        )


def list_orders(limit: int = 100) -> list[dict[str, Any]]:
    marker = param()
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM orders ORDER BY id DESC LIMIT {marker}",
            (max(1, min(int(limit), 500)),),
        ).fetchall()
        return rows_to_dicts(rows)


def record_order(
    symbol: str,
    order_type: str,
    volume: float,
    ticket: int | None = None,
    status: str | None = None,
    comment: str | None = None,
) -> None:
    marker = param()
    with get_connection() as conn:
        conn.execute(
            f"""
            INSERT INTO orders (order_time, symbol, order_type, volume, ticket, status, comment)
            VALUES ({marker}, {marker}, {marker}, {marker}, {marker}, {marker}, {marker})
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                symbol.upper(),
                order_type.upper(),
                float(volume),
                ticket,
                status,
                comment,
            ),
        )
