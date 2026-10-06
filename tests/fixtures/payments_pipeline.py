"""Payments pipeline (SQL-style, for demo). Process: ingest → clean → enrich → aggregate."""

import sqlite3
import pandas as pd


def setup_payments_db(db_path: str) -> None:
    """Create and populate the payments database for testing."""
    conn = sqlite3.connect(db_path)

    # Raw transactions table (simulated ingestion)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS raw_transactions (
        transaction_id TEXT PRIMARY KEY,
        event_ts TEXT,
        merchant_id TEXT,
        user_id TEXT,
        amount_cents INTEGER,
        currency TEXT,
        payment_method TEXT,
        status TEXT,
        error_message TEXT,
        client_version TEXT
    )
    """)
    conn.commit()


def clean(conn: sqlite3.Connection) -> pd.DataFrame:
    """Stage 2: deduplicate, remove nulls, convert units, flag errors."""
    query = """
    WITH deduped AS (
        SELECT * FROM raw_transactions
        WHERE user_id IS NOT NULL
        GROUP BY transaction_id
        HAVING event_ts = MIN(event_ts)
    ),
    filtered AS (
        SELECT * FROM deduped
        WHERE amount_cents > 0 AND amount_cents < 99999999
    )
    SELECT
        transaction_id,
        event_ts,
        merchant_id,
        user_id,
        amount_cents,
        currency,
        payment_method,
        status,
        error_message,
        client_version,
        amount_cents / 100.0 AS amount_usd,
        (error_message IS NOT NULL AND error_message LIKE '%error%') AS is_error,
        SUBSTR(client_version, 1, INSTR(client_version, '.') - 1) AS major_version
    FROM filtered
    """
    return pd.read_sql(query, conn)


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """Stage 3: add merchant region, transaction date."""
    df['transaction_date'] = pd.to_datetime(df['event_ts']).dt.date

    def get_region(merchant_id):
        if merchant_id.startswith('MER_US'):
            return 'North America'
        elif merchant_id.startswith('MER_EU'):
            return 'Europe'
        elif merchant_id.startswith('MER_APAC'):
            return 'Asia Pacific'
        return 'Other'

    df['merchant_region'] = df['merchant_id'].apply(get_region)
    return df


def aggregate(df: pd.DataFrame) -> pd.DataFrame:
    """Stage 4: daily metrics per merchant_region and payment_method."""
    return df.groupby(['transaction_date', 'merchant_region', 'payment_method']).agg(
        transaction_count=('transaction_id', 'count'),
        unique_users=('user_id', 'nunique'),
        total_volume_usd=('amount_usd', 'sum'),
        avg_transaction_usd=('amount_usd', 'mean'),
        error_rate=('is_error', 'mean'),
        decline_rate=('status', lambda x: (x == 'declined').sum() / len(x))
    ).reset_index()


def run(db_path: str) -> pd.DataFrame:
    """Full pipeline: clean → enrich → aggregate."""
    conn = sqlite3.connect(db_path)

    df = clean(conn)
    df = enrich(df)
    df = aggregate(df)

    conn.close()
    return df
