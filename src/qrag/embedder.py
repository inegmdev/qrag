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
            downloading = False
        else:
            # Bundled model absent (e.g. git+ install without pre-built wheel).
            # Fall back to HuggingFace download; give a clear message on failure.
            model_source = MODEL_NAME
            downloading = True
        try:
            _model = SentenceTransformer(model_source, device=device)
        except Exception as exc:
            _raise_model_load_error(exc, downloading=downloading)
        _model_device = device
    return _model


def _chain_has_ssl_error(exc: BaseException) -> bool:
    """Walk the full exception chain to detect SSL/certificate errors."""
    import ssl
    seen: set[int] = set()
    e: BaseException | None = exc
    while e is not None and id(e) not in seen:
        seen.add(id(e))
        if isinstance(e, ssl.SSLError):
            return True
        msg = str(e).lower()
        if any(k in msg for k in ("ssl", "certificate", "cert verify", "certificate_verify_failed")):
            return True
        e = e.__cause__ or e.__context__
    return False


def _raise_model_load_error(exc: Exception, *, downloading: bool = False) -> None:
    # Walk the full exception chain so we catch SSL errors that HuggingFace's
    # retry loop swallows — after exhausting retries, huggingface_hub raises
    # "Cannot send a request, as the client has been closed" which contains no
    # SSL keyword even though the root cause was an SSL cert failure.
    is_ssl = _chain_has_ssl_error(exc)

    # If we were fetching from HuggingFace and got any network/connection
    # error, treat it as a potential SSL/proxy issue — the retry machinery
    # may have discarded the original SSL exception.
    if not is_ssl and downloading:
        msg = str(exc).lower()
        is_ssl = any(k in msg for k in (
            "cannot send a request", "client has been closed",
            "connection error", "connection refused", "timeout",
            "proxy", "network",
        ))

    if is_ssl:
        raise RuntimeError(
            f"Failed to download the embedding model due to an SSL/network error:\n  {exc}\n\n"
            "Options to fix this:\n"
            "  1. Install the correct CA certificate for your network and retry.\n"
            "  2. Set the REQUESTS_CA_BUNDLE or CURL_CA_BUNDLE environment variable\n"
            "     to the path of your corporate/proxy CA bundle, then retry.\n"
            "  3. Download the model on a machine with unrestricted internet access:\n"
            "       python scripts/download_model.py\n"
            "     Then copy src/qrag/models/ into your qrag installation directory.\n"
            "  4. Set TRANSFORMERS_OFFLINE=1 and HF_DATASETS_OFFLINE=1 after placing\n"
            "     the model in the bundled models/ directory."
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
