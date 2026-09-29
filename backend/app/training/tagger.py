"""WD14 (SmilingWolf) ONNX tagger for danbooru-style captions."""

import csv
import threading
from pathlib import Path

_lock = threading.Lock()
_cache: dict[str, tuple] = {}

# Tags that carry no identity information and hurt caption quality.
SKIP = {"general", "sensitive", "questionable", "explicit"}


def _load(repo: str):
    with _lock:
        if repo in _cache:
            return _cache[repo]
        try:
            import onnxruntime as ort
            from huggingface_hub import hf_hub_download
        except ImportError as exc:
            raise RuntimeError("WD14 tagger needs extras: cd backend && uv sync --extra tagger") from exc
        model_path = hf_hub_download(repo, "model.onnx")
        tags_path = hf_hub_download(repo, "selected_tags.csv")
        with open(tags_path, newline="") as fh:
            rows = list(csv.DictReader(fh))
        names = [r["name"] for r in rows]
        categories = [int(r["category"]) for r in rows]
        session = ort.InferenceSession(model_path, providers=ort.get_available_providers())
        _cache[repo] = (session, names, categories)
        return _cache[repo]


def tag_image(path: Path, repo: str, threshold: float = 0.35) -> list[str]:
    import numpy as np
    from PIL import Image

    session, names, categories = _load(repo)
    inp = session.get_inputs()[0]
    size = inp.shape[1] if isinstance(inp.shape[1], int) else 448

    img = Image.open(path).convert("RGBA")
    canvas = Image.new("RGBA", img.size, (255, 255, 255, 255))
    canvas.alpha_composite(img)
    img = canvas.convert("RGB")
    side = max(img.size)
    square = Image.new("RGB", (side, side), (255, 255, 255))
    square.paste(img, ((side - img.width) // 2, (side - img.height) // 2))
    square = square.resize((size, size), Image.BICUBIC)
    arr = np.asarray(square, dtype=np.float32)[:, :, ::-1]  # RGB -> BGR
    probs = session.run(None, {inp.name: arr[None]})[0][0]

    # category 0 = general, 4 = character, 9 = rating
    scored = [
        (names[i], float(p))
        for i, p in enumerate(probs)
        if categories[i] in (0, 4) and p >= threshold and names[i] not in SKIP
    ]
    scored.sort(key=lambda x: -x[1])
    return [n.replace("_", " ") if len(n) > 3 else n for n, _ in scored]
