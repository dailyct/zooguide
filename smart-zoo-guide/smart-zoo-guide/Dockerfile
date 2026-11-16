FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY . .

# 不用 root 執行；資料庫與向量庫會寫在 backend/data 與 vector_db
RUN useradd --create-home app \
    && mkdir -p /app/vector_db \
    && chown -R app:app /app
USER app

ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}"]
