"""Local embeddings: zero per-call API cost (FIN-1413 cost rule).

BAAI/bge-small-en-v1.5 via fastembed (ONNX, CPU, 384 dims). The model is baked
into the image at build time so a cold start never downloads anything.
"""

from __future__ import annotations

import os
import threading
from typing import List, Protocol

DIM = 384
MODEL_NAME = os.environ.get("KB_EMBED_MODEL", "BAAI/bge-small-en-v1.5")
MODEL_CACHE = os.environ.get("KB_MODEL_CACHE", "/models")
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class Embedder(Protocol):
    def embed_docs(self, texts: List[str]) -> List[List[float]]: ...
    def embed_query(self, text: str) -> List[float]: ...


class LocalEmbedder:
    def __init__(self) -> None:
        self._model = None
        self._lock = threading.Lock()

    def _get(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from fastembed import TextEmbedding

                    self._model = TextEmbedding(MODEL_NAME, cache_dir=MODEL_CACHE)
        return self._model

    def embed_docs(self, texts: List[str]) -> List[List[float]]:
        return [v.tolist() for v in self._get().embed(texts)]

    def embed_query(self, text: str) -> List[float]:
        return next(iter(self._get().embed([QUERY_PREFIX + text]))).tolist()
