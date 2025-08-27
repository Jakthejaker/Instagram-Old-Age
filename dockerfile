FROM python:3.11-slim

WORKDIR /app

# system deps for psycopg2
RUN apt-get update && apt-get install -y build-essential libpq-dev gcc --no-install-recommends && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Use a small healthcheck (optional)
HEALTHCHECK --interval=1m --timeout=5s --start-period=30s CMD curl -f http://localhost:10000/ping-test || exit 1

CMD ["python", "bot.py"]
