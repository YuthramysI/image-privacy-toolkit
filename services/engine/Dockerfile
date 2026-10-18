FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/models/hf \
    TORCH_HOME=/models/torch

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir --no-deps facenet-pytorch==2.6.0

COPY engine ./engine

# Descarga los pesos en la imagen para que el primer trabajo no espere.
RUN python -c "from engine.protect.pipeline import Engine; Engine()"

EXPOSE 8000
CMD ["uvicorn", "engine.api:app", "--host", "0.0.0.0", "--port", "8000"]
