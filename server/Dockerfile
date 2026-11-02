FROM python:3.13-slim
WORKDIR /app
COPY sdk-python /app/sdk-python
RUN pip install --no-cache-dir /app/sdk-python fastapi "uvicorn[standard]" "sqlalchemy>=2" "psycopg[binary]" psycopg_pool reportlab httpx pyyaml anthropic
COPY server /app/server
WORKDIR /app/server
ENV PYTHONPATH=/app/server
CMD ["sh","-c","python -c 'from app import db; db.init_schema()' && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
