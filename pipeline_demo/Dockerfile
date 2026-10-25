FROM python:3.11-slim

WORKDIR /app

COPY pipeline_demo /app/pipeline_demo
COPY pipelines/user_behavior/src /app/user_behavior

RUN pip install --no-cache-dir "fastapi>=0.110,<1" "uvicorn>=0.29,<1" "pandas>=2.2,<3" "minio>=7.2,<8"

ENV PYTHONPATH=/app/user_behavior
ENV PYTHONUNBUFFERED=1
EXPOSE 3000

CMD ["uvicorn", "pipeline_demo.server:app", "--host", "0.0.0.0", "--port", "3000"]
