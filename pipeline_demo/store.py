"""Write stage frames for the shipment ledger into Postgres."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd
import psycopg
from psycopg import sql


def store_stage_tables(
    dsn: str,
    pipeline_id: str,
    frames: dict[str, pd.DataFrame],
    stages: tuple[str, ...],
    run_id: str,
) -> list[str]:
    """Append each stage frame to ``{pipeline_id}_{stage}`` and return table locations."""
    if not dsn.strip():
        raise ValueError("STAGE_DATABASE_URL is empty")
    if not pipeline_id.isidentifier():
        raise ValueError(f"pipeline id is not an identifier: {pipeline_id}")
    locations: list[str] = []
    with psycopg.connect(dsn) as conn:
        for stage in stages:
            if not stage.isidentifier():
                raise ValueError(f"stage name is not an identifier: {stage}")
            table = f"{pipeline_id}_{stage}"
            frame = frames[stage].copy()
            frame.insert(0, "run_id", run_id)
            _ensure_table(conn, table, frame)
            _insert_frame(conn, table, frame)
            locations.append(f"db://{table}")
        conn.commit()
    return locations


def _ensure_table(conn: psycopg.Connection[tuple[Any, ...]], table: str, frame: pd.DataFrame) -> None:
    columns = [_column_type(name, frame[name]) for name in frame.columns]
    statement = sql.SQL("CREATE TABLE IF NOT EXISTS {} ({})").format(
        sql.Identifier(table),
        sql.SQL(", ").join(columns),
    )
    conn.execute(statement)


def _column_type(name: str, series: pd.Series) -> sql.Composed:
    if not name.isidentifier():
        raise ValueError(f"column name is not an identifier: {name}")
    if name == "run_id":
        kind = "TEXT"
    elif pd.api.types.is_bool_dtype(series):
        kind = "BOOLEAN"
    elif pd.api.types.is_integer_dtype(series):
        kind = "BIGINT"
    elif pd.api.types.is_float_dtype(series):
        kind = "DOUBLE PRECISION"
    else:
        kind = "TEXT"
    return sql.SQL("{} {}").format(sql.Identifier(name), sql.SQL(kind))


def _insert_frame(conn: psycopg.Connection[tuple[Any, ...]], table: str, frame: pd.DataFrame) -> None:
    if frame.empty:
        return
    columns = list(frame.columns)
    statement = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
        sql.Identifier(table),
        sql.SQL(", ").join(sql.Identifier(name) for name in columns),
        sql.SQL(", ").join(sql.Placeholder() for _ in columns),
    )
    rows = [tuple(_python_value(value) for value in row) for row in frame.itertuples(index=False, name=None)]
    with conn.cursor() as cur:
        cur.executemany(statement, rows)


def _python_value(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    item = getattr(value, "item", None)
    if callable(item):
        try:
            converted = item()
        except (ValueError, TypeError):
            return None if _is_missing(value) else str(value)
        if isinstance(converted, float) and math.isnan(converted):
            return None
        return converted
    if _is_missing(value):
        return None
    return value


def _is_missing(value: object) -> bool:
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        return False
    return bool(missing)
