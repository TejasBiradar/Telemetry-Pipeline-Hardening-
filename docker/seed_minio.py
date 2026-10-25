"""Upload clean + bad CSV dumps into MinIO using the fixed {prefix}/{stage}/ layout."""

from __future__ import annotations

import argparse
import io
import os

import pandas as pd
from minio import Minio


def _client() -> Minio:
    endpoint = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
    endpoint = endpoint.replace("https://", "").replace("http://", "")
    return Minio(
        endpoint,
        access_key=os.environ.get("MINIO_ACCESS_KEY", "minioadmin"),
        secret_key=os.environ.get("MINIO_SECRET_KEY", "minioadmin"),
        secure=False,
    )


def _upload_csv(client: Minio, bucket: str, key: str, df: pd.DataFrame) -> None:
    buf = io.BytesIO(df.to_csv(index=False).encode("utf-8"))
    client.put_object(bucket, key, buf, length=buf.getbuffer().nbytes, content_type="text/csv")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pipeline-id", default="demo")
    parser.add_argument("--bucket", default="demo")
    parser.add_argument("--prefix", default="demo/user_behavior/outputs")
    args = parser.parse_args()

    prefix = args.prefix.strip("/")
    client = _client()
    if not client.bucket_exists(args.bucket):
        client.make_bucket(args.bucket)

    # Enough rows for null-rate checks (MIN_SAMPLE_SIZE=30).
    n = 40
    clean = pd.DataFrame(
        {
            "session_id": [f"s{i}" for i in range(n)],
            "user_id": [f"u{i}" for i in range(n)],
            "duration_ms": list(range(n)),
        }
    )
    bad = clean.copy()
    bad.loc[:, "user_id"] = None  # should fail required/null-style checks if confirmed

    _upload_csv(client, args.bucket, f"{prefix}/ingest/batch_clean.csv", clean)
    _upload_csv(client, args.bucket, f"{prefix}/ingest/batch_bad_nulls.csv", bad)
    _upload_csv(client, args.bucket, f"{prefix}/aggregate/batch_clean.csv", clean)
    print(f"uploaded under s3://{args.bucket}/{prefix}/{{ingest,aggregate}}/")


if __name__ == "__main__":
    main()
