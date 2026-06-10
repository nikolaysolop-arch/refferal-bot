FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir python-telegram-bot==13.7 flask

COPY bot.py app.py ./

CMD ["python", "app.py"]
