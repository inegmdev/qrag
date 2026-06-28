"""Download all-MiniLM-L6-v2 ONNX model into src/qrag/models/ for wheel bundling.

Run this once before building the wheel:

    uv run python scripts/download_model.py
    uv build
"""
import pathlib
from huggingface_hub import hf_hub_download

DEST = pathlib.Path("src/qrag/models/all-MiniLM-L6-v2")
DEST.mkdir(parents=True, exist_ok=True)

FILES = ["tokenizer.json", "tokenizer_config.json", "onnx/model.onnx"]

print(f"Downloading model → {DEST} ...")
for filename in FILES:
    print(f"  {filename}")
    hf_hub_download(
        repo_id="Xenova/all-MiniLM-L6-v2",
        filename=filename,
        local_dir=str(DEST),
    )
print("Done.")
