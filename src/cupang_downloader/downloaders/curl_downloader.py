import os
from pathlib import Path
from threading import Event

from .._default import default_cacert
from .base import DownloaderBase, DownloaderSubprocessMixin


class CurlDownloader(DownloaderSubprocessMixin, DownloaderBase):
    """CurlDownloader uses `curl` to download files."""

    def __init__(self, curl_bin: str | Path = None, cancel_event: Event = None, chunk_size: int = None) -> None:
        """
        Args:
            curl_bin (str | Path, optional): Path to the curl binary. Defaults to None.
            cancel_event (Event, optional): Event to signal download cancellation. Defaults to None.
            chunk_size (int, optional): Size of each chunk to be downloaded. Defaults to None.
        """
        self.bin = self.check_bin(curl_bin or ("curl" if os.name != "nt" else "curl.exe"))
        self.cmd = [str(self.bin), "-sLo-"]
        self.opt = ["--cacert", str(default_cacert)]
        super().__init__(cancel_event, chunk_size)

    def download(
        self,
        job,
        progress_callback,
    ):
        """
        Execute the download process for a given job.

        Args:
            job (DownloadJob): The download job containing details such as URL, headers, output destination, etc.
            progress_callback (Callable[[DownloadJob, TotalInt, DownloadedInt, ExtraDict], None | Any]):
                A callback function to handle progress updates.

        Raises:
            BaseException: Any exceptions related to the download process will be propagated as needed.
        """
        if self.is_canceled:
            return

        with self.request(job.url, headers=job.headers) as res:
            total = int(res.getheader("Content-Length", 0))

        cmd_headers = [f'-H "{x}: {y}"' for x, y in job.headers.items()]

        with (
            self.popen_wrapper(self.cmd + self.opt + cmd_headers + [job.url]) as p,
            job.out.open("wb") as f,
        ):
            downloaded = 0
            while p.poll() is None and not self.is_canceled:
                chunk = p.stdout.read(self.chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)

                self._handle_progress(progress_callback, job, total, downloaded)
