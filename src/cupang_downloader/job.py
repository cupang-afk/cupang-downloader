from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any


@dataclass
class DownloadJob:
    """
    A class to contain anything related to the download.

    Attributes:
        url (str): The URL of the file to be downloaded.
        out (IO[bytes] | Path | str | None, optional): The output stream or path
            where the downloaded file will be saved. If this is `str` will try to convert to `pathlib.Path`
            Defaults to None.
        headers (dict[str, str] | None, optional): Optional headers to include in the download request.
            Defaults to None.
        progress_name (str, optional): The name to be used for displaying progress.
            If not set, then will try to use `out.name` or `url` instead.
            Defaults to None.
        extra (dict[str, Any] | None, optional): Any additional data associated with the download job.
            Defaults to None.
    """

    url: str
    out: IO[bytes] | Path | str | None = None
    headers: dict[str, str] | None = None
    progress_name: str = None
    extra: dict[str, Any] | None = None

    def __post_init__(self):
        self.out = (
            self.out if isinstance(self.out, Path) else Path(self.out) if isinstance(self.out, str) else self.out
        )
        self.progress_name = self.progress_name or (self.out.name if isinstance(self.out, Path) else self.url)

    def copy_with_new_value(
        self,
        url: str = None,
        out: IO[bytes] | Path | None = None,
        headers: dict[str, str] | None = None,
        progress_name: str = None,
        extra: dict[str, Any] | None = None,
    ):
        if self.extra is not None:
            self.extra.update(extra or {})
        else:
            self.extra = extra

        return DownloadJob(
            url or self.url,
            out or self.out,
            headers or self.headers,
            progress_name or self.progress_name,
            self.extra,
        )
