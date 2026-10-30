FROM python:3.11-slim

WORKDIR /app

COPY pipeline_demo /app/pipeline_demo
COPY pipelines/user_behavior/src /app/pipeline_src/user_behavior
COPY pipelines/payment_processing/src /app/pipeline_src/payment_processing
COPY pipelines/shipment_ledger/sql /app/pipeline_src/shipment_ledger
COPY pipelines/web_analytics/legacy /app/pipeline_src/web_analytics

RUN pip install --no-cache-dir "fastapi>=0.110,<1" "uvicorn>=0.29,<1" "pandas>=2.2,<3" "minio>=7.2,<8" "psycopg[binary]>=3.1,<4"

ENV PYTHONPATH=/app
ENV PIPELINE_SRC_ROOT=/app/pipeline_src
ENV PYTHONUNBUFFERED=1
EXPOSE 3000

CMD ["uvicorn", "pipeline_demo.server:app", "--host", "0.0.0.0", "--port", "3000"]
