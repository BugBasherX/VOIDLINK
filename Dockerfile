FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default port (overridden per-service in docker-compose.yml)
EXPOSE 5000

ENTRYPOINT ["python3", "node.py"]
