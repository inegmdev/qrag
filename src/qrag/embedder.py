from __future__ import annotations

import pathlib
import struct
from typing import Sequence

import numpy as np

_session = None
_tokenizer = None
MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384
_MAX_LENGTH = 128

_BUNDLED_MODEL = pathlib.Path(__file__).parent / "models" / MODEL_NAME
_RUNTIME_MODEL = pathlib.Path.home() / ".qrag" / "models" / MODEL_NAME
_HF_REPO = f"Xenova/{MODEL_NAME}"
_MODEL_FILES = ["tokenizer.json", "tokenizer_config.json", "onnx/model.onnx"]


def resolve_device(requested: str) -> str:
    """Return 'cpu'. Device parameter is kept for CLI compatibility."""
    if requested == "cuda":
        raise ValueError(
            "CUDA requested but the onnxruntime-cpu backend does not support GPU inference. "
            "Install onnxruntime-gpu to enable GPU acceleration."
        )
    return "cpu"


def default_batch_size(device: str) -> int:
    return 256


def _locate_model_dir() -> pathlib.Path | None:
    for candidate in (_BUNDLED_MODEL, _RUNTIME_MODEL):
        if (candidate / "onnx" / "model.onnx").is_file() and (candidate / "tokenizer.json").is_file():
            return candidate
    return None


def _chain_has_ssl_error(exc: BaseException) -> bool:
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
            f"     Then copy the model files to ~/.qrag/models/{MODEL_NAME}/\n"
            "  4. Set HF_DATASETS_OFFLINE=1 after placing the model files at\n"
            f"     ~/.qrag/models/{MODEL_NAME}/onnx/model.onnx"
        ) from None
    raise RuntimeError(
        f"Failed to load the embedding model: {exc}\n\n"
        "Try reinstalling qrag:\n"
        "  uv tool install git+https://github.com/inegmdev/qrag.git@main"
    ) from None


def _download_model() -> pathlib.Path:
    from huggingface_hub import hf_hub_download

    _RUNTIME_MODEL.mkdir(parents=True, exist_ok=True)
    try:
        for filename in _MODEL_FILES:
            hf_hub_download(
                repo_id=_HF_REPO,
                filename=filename,
                local_dir=str(_RUNTIME_MODEL),
            )
    except Exception as exc:
        _raise_model_load_error(exc, downloading=True)
    return _RUNTIME_MODEL


def _load():
    global _session, _tokenizer
    if _session is not None:
        return _session, _tokenizer

    from tokenizers import Tokenizer
    import onnxruntime as ort

    model_dir = _locate_model_dir()
    if model_dir is None:
        model_dir = _download_model()

    tok_path = model_dir / "tokenizer.json"
    onnx_path = model_dir / "onnx" / "model.onnx"

    try:
        tok = Tokenizer.from_file(str(tok_path))
        tok.enable_padding(pad_id=0, pad_token="[PAD]", length=_MAX_LENGTH)
        tok.enable_truncation(max_length=_MAX_LENGTH)
    except Exception as exc:
        _raise_model_load_error(exc)

    try:
        sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    except Exception as exc:
        _raise_model_load_error(exc)

    _tokenizer = tok
    _session = sess
    return _session, _tokenizer


def _mean_pool(last_hidden: np.ndarray, attention_mask: np.ndarray) -> np.ndarray:
    mask = attention_mask[:, :, np.newaxis].astype(np.float32)
    summed = (last_hidden * mask).sum(axis=1)
    counts = mask.sum(axis=1).clip(min=1e-9)
    return summed / counts


def _l2_normalize(x: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(x, axis=1, keepdims=True).clip(min=1e-9)
    return x / norms


def embed(texts: Sequence[str], device: str = "cpu", precision: str = "float32") -> list[list[float]]:
    session, tokenizer = _load()

    encodings = tokenizer.encode_batch(list(texts))
    input_ids = np.array([enc.ids for enc in encodings], dtype=np.int64)
    attention_mask = np.array([enc.attention_mask for enc in encodings], dtype=np.int64)
    token_type_ids = np.array([enc.type_ids for enc in encodings], dtype=np.int64)

    input_names = {inp.name for inp in session.get_inputs()}
    feed: dict[str, np.ndarray] = {
        "input_ids": input_ids,
        "attention_mask": attention_mask,
    }
    if "token_type_ids" in input_names:
        feed["token_type_ids"] = token_type_ids

    outputs = session.run(None, feed)
    primary = outputs[0]

    # Handle both raw hidden states (needs pooling) and pre-pooled sentence embeddings
    if primary.ndim == 3:
        pooled = _mean_pool(primary, attention_mask)
        result = _l2_normalize(pooled).astype(np.float32)
    else:
        result = _l2_normalize(primary).astype(np.float32)

    return result.tolist()


def embed_one(text: str, device: str = "cpu") -> list[float]:
    return embed([text], device=device)[0]


def to_blob(embedding: list[float]) -> bytes:
    return struct.pack(f"{len(embedding)}f", *embedding)


def from_blob(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))
