FROM python:3.12.14-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN adduser --disabled-password --gecos "" appuser && \
    mkdir -p /app && \
    chown -R appuser:appuser /app

COPY . .

USER appuser

ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV PATH="/home/appuser/.local/bin:${PATH}"

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
