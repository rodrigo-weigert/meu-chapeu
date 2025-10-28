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

    def is_downloaded(self) -> bool:
        return self.file_path.is_file()

    def download(self) -> bool:
        return self.is_downloaded() or self.download_fn()

    def duration_str(self) -> str:
        return f"{self.duration // 60}:{self.duration % 60:%02d}"
