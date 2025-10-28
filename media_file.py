import os

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True, kw_only=True)
class MediaFile:
    id: str
    file_path: str
    title: str
    thumbnail: str
    duration: int
    link: str
    download_fn: Callable[[], bool] = field(repr=False)

    def is_downloaded(self) -> bool:
        return os.path.isfile(self.file_path)

    def download(self) -> bool:
        return self.is_downloaded() or self.download_fn()
