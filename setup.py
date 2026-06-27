"""Custom build hook: bundle all-MiniLM-L6-v2 into the wheel at build time.

When a developer runs `uv build` or a user installs via `git+`, this
downloads the model from HuggingFace into the build directory so it is
shipped inside the wheel.  If the network is unreachable (e.g. a corporate
proxy with a self-signed certificate) the hook warns and exits cleanly;
the wheel is built without the model and the runtime fallback in
embedder.py handles the error with actionable guidance.

To suppress the download (e.g. CI environments where the model is already
present in src/qrag/models/), set QRAG_SKIP_MODEL_DOWNLOAD=1.
"""
from __future__ import annotations

import os
import pathlib
import shutil

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py

MODEL_NAME = "all-MiniLM-L6-v2"
MODEL_REPO = f"sentence-transformers/{MODEL_NAME}"
_SRC_MODEL = pathlib.Path("src/qrag/models") / MODEL_NAME


class build_py(_build_py):
    def run(self) -> None:
        super().run()
        self._bundle_model()

    def _bundle_model(self) -> None:
        if os.environ.get("QRAG_SKIP_MODEL_DOWNLOAD"):
            return

        if not _SRC_MODEL.is_dir():
            print(f"[qrag] Downloading embedding model {MODEL_NAME} for bundling…", flush=True)
            try:
                from huggingface_hub import snapshot_download
                _SRC_MODEL.parent.mkdir(parents=True, exist_ok=True)
                snapshot_download(
                    repo_id=MODEL_REPO,
                    local_dir=str(_SRC_MODEL),
                    local_dir_use_symlinks=False,
                    ignore_patterns=["*.msgpack", "*.h5", "flax_*", "tf_*", "rust_*"],
                )
                print("[qrag] Model downloaded and ready to bundle.", flush=True)
            except Exception as exc:
                print(f"[qrag] WARNING: Could not download model during build: {exc}", flush=True)
                print(
                    "[qrag] The wheel will be built without a bundled model.\n"
                    "[qrag] At runtime, set REQUESTS_CA_BUNDLE to your CA bundle path\n"
                    "[qrag] or use `python scripts/download_model.py` on an unrestricted machine.",
                    flush=True,
                )
                return

        dest = pathlib.Path(self.build_lib) / "qrag" / "models" / MODEL_NAME
        if dest.exists():
            return
        print(f"[qrag] Bundling model into wheel ({_SRC_MODEL} → {dest})…", flush=True)
        shutil.copytree(str(_SRC_MODEL), str(dest))


setup(cmdclass={"build_py": build_py})
