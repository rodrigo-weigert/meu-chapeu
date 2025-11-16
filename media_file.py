import asyncio
import pickle

from dataclasses import dataclass, field
from typing import Callable
from pathlib import Path


@dataclass(frozen=True, kw_only=True)
class MediaFile:
    id: str
    file_path: Path
    title: str
    thumbnail: str
    duration: int
    link: str
    download_fn: Callable[[], bool] = field(repr=False)
    downloaded: asyncio.Future = field(init=False, repr=False)

    def download(self) -> bool:
        if self.downloaded.done():
            return self.downloaded.result()

        result = self.download_fn()
        self.downloaded.set_result(result)
        return result

    def duration_str(self) -> str:
        return f"{self.duration // 60}:{self.duration % 60:02d}"

    def packets(self) -> list[bytes]:
        with open(self.file_path, "rb") as f:
            return pickle.load(f)

    def __post_init__(self):
        object.__setattr__(self, "downloaded", asyncio.get_running_loop().create_future())
