import random
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from PIL import Image

ProgressFn = Callable[[float, str], None]


class GenerationCancelled(Exception):
    pass


@dataclass
class LoraSpec:
    path: Path
    weight: float
    name: str


@dataclass
class ImageRequest:
    prompt: str
    negative_prompt: str = ""
    width: int = 1216
    height: int = 832
    steps: int = 28
    cfg: float = 6.0
    seed: int = -1
    num_images: int = 1
    checkpoint: str = ""
    loras: list[LoraSpec] = field(default_factory=list)
    mode: Literal["txt2img", "img2img", "inpaint"] = "txt2img"
    init_image: Path | None = None
    mask_image: Path | None = None
    strength: float = 0.6
    ip_adapter_images: list[Path] = field(default_factory=list)
    ip_adapter_scale: float = 0.6

    def resolved_seed(self) -> int:
        if self.seed is None or self.seed < 0:
            self.seed = random.randint(0, 2**31 - 1)
        return self.seed


@dataclass
class GeneratedImage:
    image: Image.Image
    seed: int


class ImageBackend(Protocol):
    name: str
    supports_lora: bool
    supports_ip_adapter: bool

    def generate(
        self, req: ImageRequest, progress: ProgressFn, cancel: threading.Event
    ) -> list[GeneratedImage]: ...

    def list_models(self) -> list[str]: ...

    def status(self) -> dict: ...

    def unload(self) -> None: ...
