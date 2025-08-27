# Use Python image
FROM python:3.11-slim

# Set work directory
WORKDIR /app

# Copy files
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run gunicorn with Flask
CMD ["gunicorn", "-b", "0.0.0.0:5000", "bot:app"]
