FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY most_bot/ most_bot/

CMD ["python", "-m", "most_bot", "--config", "/app/config/config.yaml"]
