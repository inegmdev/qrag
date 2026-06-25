from __future__ import annotations

import pathlib
import struct
from typing import Sequence

_model = None
_model_device: str | None = None
MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

_BUNDLED_MODEL = pathlib.Path(__file__).parent / "models" / MODEL_NAME


def resolve_device(requested: str) -> str:
    """Return 'cuda' or 'cpu'. Raises ValueError if cuda is requested but unavailable."""
    if requested == "cpu":
        return "cpu"
    if requested == "cuda":
        try:
            import torch
            if not torch.cuda.is_available():
                raise ValueError("CUDA requested but torch reports no CUDA device available")
            return "cuda"
        except ImportError:
            raise ValueError("CUDA requested but torch is not installed")
    # auto
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


def _get_model(device: str = "cpu"):
    global _model, _model_device
    if _model is None or _model_device != device:
        from sentence_transformers import SentenceTransformer
        if _BUNDLED_MODEL.is_dir():
            model_source = str(_BUNDLED_MODEL)
        else:
            # Bundled model absent (e.g. git+ install without pre-built wheel).
            # Fall back to HuggingFace download; give a clear message on failure.
            model_source = MODEL_NAME
        try:
            _model = SentenceTransformer(model_source, device=device)
        except Exception as exc:
            _raise_model_load_error(exc)
        _model_device = device
    return _model


def _raise_model_load_error(exc: Exception) -> None:
    msg = str(exc).lower()
    if any(k in msg for k in ("ssl", "certificate", "cert", "proxy")):
        raise RuntimeError(
            f"Failed to download the embedding model due to an SSL/certificate error:\n  {exc}\n\n"
            "Options to fix this:\n"
            "  1. Install the correct CA certificate for your network and retry.\n"
            "  2. Set the REQUESTS_CA_BUNDLE environment variable to your CA bundle path.\n"
            "  3. Download the model manually on a machine with internet access:\n"
            "       python scripts/download_model.py\n"
            "     Then copy src/qrag/models/ into your qrag installation directory."
        ) from None
    raise RuntimeError(
        f"Failed to load the embedding model: {exc}\n\n"
        "Try reinstalling qrag:\n"
        "  uv tool install git+https://github.com/inegmdev/qrag.git@main"
    ) from None


def default_batch_size(device: str) -> int:
    """Return a device-appropriate default embedding batch size."""
    return 1024 if device == "cuda" else 256


def embed(texts: Sequence[str], device: str = "cpu", precision: str = "float32") -> list[list[float]]:
    model = _get_model(device)
    return model.encode(list(texts), convert_to_numpy=True, precision=precision).tolist()


def embed_one(text: str, device: str = "cpu") -> list[float]:
    return embed([text], device=device)[0]


def to_blob(embedding: list[float]) -> bytes:
    return struct.pack(f"{len(embedding)}f", *embedding)


def from_blob(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))
