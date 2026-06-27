"""Build hook: ensure the bundled model is real, not an LFS pointer.

The all-MiniLM-L6-v2 model is stored in src/qrag/models/ via Git LFS.
When a user clones/installs with git-lfs installed, the real files are
present and this hook just copies them into the wheel — no network call.

If git-lfs is NOT installed, binary files are replaced by small LFS
pointer text files.  This hook detects that case and falls back to
downloading the model directly from HuggingFace, with a clear warning.

Set QRAG_SKIP_MODEL_DOWNLOAD=1 to bypass the download fallback entirely
(the wheel will be built without a bundled model and the runtime error
path in embedder.py will handle it with actionable guidance).
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
_LFS_POINTER_MARKER = b"version https://git-lfs.github.com"


def _is_lfs_pointer(path: pathlib.Path) -> bool:
    """Return True if the file is an LFS pointer stub, not the real binary."""
    try:
        with path.open("rb") as f:
            return f.read(64).startswith(_LFS_POINTER_MARKER)
    except OSError:
        return False


def _model_is_real(model_dir: pathlib.Path) -> bool:
    """Return True only when the model directory contains actual weight files."""
    for ext in ("*.bin", "*.safetensors", "*.pt", "*.onnx"):
        for candidate in model_dir.glob(ext):
            if _is_lfs_pointer(candidate):
                return False
            return True  # found a real weight file
    return False  # no weight file at all


class build_py(_build_py):
    def run(self) -> None:
        super().run()
        self._bundle_model()

    def _bundle_model(self) -> None:
        if _model_is_real(_SRC_MODEL):
            # Happy path: git-lfs pulled real files — just copy into the wheel.
            dest = pathlib.Path(self.build_lib) / "qrag" / "models" / MODEL_NAME
            if not dest.exists():
                shutil.copytree(str(_SRC_MODEL), str(dest))
            return

        if os.environ.get("QRAG_SKIP_MODEL_DOWNLOAD"):
            return

        # LFS pointers or missing dir — git-lfs was probably not installed.
        print(
            "[qrag] WARNING: model files look like LFS pointers or are missing.\n"
            "[qrag] Install git-lfs (https://git-lfs.com) for a faster, "
            "offline-capable install.\n"
            "[qrag] Falling back to HuggingFace download…",
            flush=True,
        )

        try:
            from huggingface_hub import snapshot_download
            _SRC_MODEL.parent.mkdir(parents=True, exist_ok=True)
            snapshot_download(
                repo_id=MODEL_REPO,
                local_dir=str(_SRC_MODEL),
                local_dir_use_symlinks=False,
                ignore_patterns=["*.msgpack", "*.h5", "flax_*", "tf_*", "rust_*"],
            )
        except Exception as exc:
            print(
                f"[qrag] WARNING: HuggingFace download failed: {exc}\n"
                "[qrag] The wheel will be built without a bundled model.\n"
                "[qrag] At runtime set REQUESTS_CA_BUNDLE to your CA bundle path,\n"
                "[qrag] or install git-lfs and reinstall qrag.",
                flush=True,
            )
            return

        dest = pathlib.Path(self.build_lib) / "qrag" / "models" / MODEL_NAME
        if not dest.exists():
            shutil.copytree(str(_SRC_MODEL), str(dest))


setup(cmdclass={"build_py": build_py})
