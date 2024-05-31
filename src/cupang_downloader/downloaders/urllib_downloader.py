from ..utils import request
from .base import DownloaderBase


class UrllibDownloader(DownloaderBase):
    """UrllibDownloader uses built-in `urllib` module to download files."""

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
        with request(job.url, headers=job.headers) as res, job.out.open("wb") as f:
            total = int(res.getheader("Content-Length", 0))

            downloaded = 0
            while not self.is_canceled:
                chunk = res.read(self.chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)

                self._handle_progress(progress_callback, job, total, downloaded)
