"""Read one stage table. The connection string stays in the environment."""

from __future__ import annotations

import hashlib
import os

import pandas as pd

from teleguard.onboard.output_store import (
    MinioOutputStore,
    validate_column_name,
    validate_table_name,
)


def read_table(store: MinioOutputStore, table: str, *, stage: str | None = None) -> pd.DataFrame:
    """Load rows for one stage.

    ``per_table`` reads the whole declared table. ``shared_table`` keeps rows whose
    stage column equals ``stage``. The stage value is a bound parameter.
    """
    import psycopg

    name = validate_table_name(table)
    dsn = os.environ.get(store.dsn_env, "")
    if not dsn:
        raise RuntimeError(f"set {store.dsn_env} for the stage database")
    quoted = ".".join(f'"{part}"' for part in name.split("."))
    params: tuple[str, ...] = ()
    if store.db_layout == "shared_table":
        if stage is None:
            raise ValueError("shared table layout needs the stage name")
        column = validate_column_name(store.stage_column)
        query = f'SELECT * FROM {quoted} WHERE "{column}" = %s'
        params = (stage,)
    else:
        query = f"SELECT * FROM {quoted}"
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(query, params)
        columns = [desc.name for desc in cur.description or ()]
        rows = cur.fetchall()
    return pd.DataFrame(rows, columns=columns)


def table_fingerprint(frame: pd.DataFrame) -> str:
    """Stable id for the current table contents, so an unchanged table is not rechecked."""
    payload = frame.to_csv(index=False).encode()
    return hashlib.sha256(payload).hexdigest()[:16]
