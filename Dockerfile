FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# data/ монтируется как volume снаружи — не копируем
RUN mkdir -p data/logs

CMD ["python", "bot.py", "start"]
