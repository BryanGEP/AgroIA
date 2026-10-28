FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY web ./web
# Ingesta del RAG: se corre aparte con `python -m ingesta.cargar` (ver README)
COPY ingesta ./ingesta
COPY conocimiento ./conocimiento

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
