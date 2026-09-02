FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY config.yaml ./config.yaml
RUN mkdir -p /data

CMD ["python", "-m", "app.main", "--config", "/app/config.yaml"]
