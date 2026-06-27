"""Download all-MiniLM-L6-v2 into src/qrag/models/ for wheel bundling.

Run this once before building the wheel:
    uv run python scripts/download_model.py
    uv build
"""
import pathlib
from sentence_transformers import SentenceTransformer

DEST = pathlib.Path("src/qrag/models/all-MiniLM-L6-v2")
DEST.mkdir(parents=True, exist_ok=True)
print(f"Downloading model → {DEST} ...")
SentenceTransformer("all-MiniLM-L6-v2").save(str(DEST))
print("Done.")
