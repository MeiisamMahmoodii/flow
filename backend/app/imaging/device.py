from ..config import get_settings

INSTALL_HINT = "Image support is not installed. Run: cd backend && uv sync --extra image"


def torch_available() -> bool:
    try:
        import torch  # noqa: F401

        return True
    except ImportError:
        return False


def pick_device() -> str:
    import torch

    pref = get_settings().device
    if pref != "auto":
        return pref
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def pick_dtype(device: str):
    import torch

    pref = get_settings().dtype
    if pref != "auto":
        return getattr(torch, pref)
    if device in ("cuda", "mps"):
        return torch.float16
    return torch.float32


def device_info() -> dict:
    if not torch_available():
        return {"torch": False, "device": None, "hint": INSTALL_HINT}
    import torch

    dev = pick_device()
    info: dict = {"torch": True, "torch_version": torch.__version__, "device": dev, "dtype": str(pick_dtype(dev))}
    if dev == "cuda":
        props = torch.cuda.get_device_properties(0)
        info["gpu"] = props.name
        info["vram_gb"] = round(props.total_memory / 1024**3, 1)
    return info
