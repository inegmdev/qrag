from __future__ import annotations

import struct
from typing import Sequence

_model = None
MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed(texts: Sequence[str]) -> list[list[float]]:
    model = _get_model()
    return model.encode(list(texts), convert_to_numpy=True).tolist()


def embed_one(text: str) -> list[float]:
    return embed([text])[0]


def to_blob(embedding: list[float]) -> bytes:
    return struct.pack(f"{len(embedding)}f", *embedding)


def from_blob(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))
