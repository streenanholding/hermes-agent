FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 KB_MODEL_CACHE=/models
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake the embedding model into the image so startup never downloads anything.
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/models')"

COPY agent_kb ./agent_kb
COPY kb_admin.py .

RUN useradd --system --uid 10001 kb && chown -R kb /models
USER kb

CMD ["python", "-m", "agent_kb.app"]
