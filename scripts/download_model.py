"""Download all-MiniLM-L6-v2 into src/qrag/models/ for wheel bundling.

Run this once before building the wheel, or use the GitHub Actions
workflow .github/workflows/bundle-model.yml to commit the model via LFS:

    uv run python scripts/download_model.py
    uv build
"""
import pathlib
from huggingface_hub import snapshot_download

DEST = pathlib.Path("src/qrag/models/all-MiniLM-L6-v2")
DEST.parent.mkdir(parents=True, exist_ok=True)
print(f"Downloading model → {DEST} ...")
snapshot_download(
    repo_id="sentence-transformers/all-MiniLM-L6-v2",
    local_dir=str(DEST),
    ignore_patterns=["*.msgpack", "*.h5", "flax_*", "tf_*", "rust_*"],
)
print("Done.")
