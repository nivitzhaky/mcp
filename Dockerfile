FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/credentials

EXPOSE 8000 8080

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "/app"]
