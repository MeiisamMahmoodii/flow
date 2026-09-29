import threading

from ..config import get_settings
from .base import ImageBackend

_lock = threading.Lock()
_instances: dict[str, ImageBackend] = {}


def get_backend(name: str | None = None) -> ImageBackend:
    name = name or get_settings().image_backend
    with _lock:
        if name not in _instances:
            if name == "comfyui":
                from .comfy_backend import ComfyUIBackend

                _instances[name] = ComfyUIBackend()
            else:
                from .diffusers_backend import DiffusersBackend

                _instances[name] = DiffusersBackend()
        return _instances[name]


def unload_all() -> None:
    with _lock:
        for backend in _instances.values():
            backend.unload()
