import requests

from .._default import default_cacert
from .base import DownloaderBase


class RequestsDownloader(DownloaderBase):
    """RequestsDownloader uses `requests` module to download files."""

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
        if self.is_cancelled:
            return
        with (
            requests.get(
                job.url,
                headers=job.headers,
                stream=True,
                verify=str(default_cacert),
            ) as res,
            job.out.open("wb") as f,
        ):
            res.raise_for_status()
            total = int(res.getheader("Content-Length", 0))

            downloaded = 0
            for chunk in res.iter_content(self.chunk_size):
                if self.is_canceled:
                    break
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)

                self._handle_progress(progress_callback, job, total, downloaded)
