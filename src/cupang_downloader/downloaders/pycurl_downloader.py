import pycurl

from .._default import default_cacert
from .base import DownloaderBase


class PycurlDownloader(DownloaderBase):
    """PycurlDownloader uses `pycurl` module to download files."""

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
            total = res.getheader("Content-Length", None)
            if total is not None:
                total = int(total)

        callback_error: Exception = None

        def _callback(_, d, *__):
            try:
                if self.is_canceled:
                    return 1

                nonlocal callback_error
                return self._handle_progress(progress_callback, job, total, d)
            except (BaseException, Exception, KeyboardInterrupt) as e:
                callback_error = e
                return 1

        with job.out.open("wb") as f:
            curl = pycurl.Curl()
            curl.setopt(curl.URL, job.url)
            curl.setopt(curl.WRITEDATA, f)
            curl.setopt(curl.FOLLOWLOCATION, True)
            curl.setopt(
                curl.HTTPHEADER,
                [f"{k}: {v}" for k, v in {**job.headers}.items()],
            )
            curl.setopt(curl.CAINFO, str(default_cacert))
            curl.setopt(curl.BUFFERSIZE, self.chunk_size)
            curl.setopt(curl.NOPROGRESS, False)
            curl.setopt(
                curl.XFERINFOFUNCTION,
                _callback,
            )

            error = None
            try:
                curl.perform()
            except Exception as e:
                error = e
            finally:
                curl.close()

            if callback_error is not None and not self.is_canceled:
                raise callback_error.with_traceback(callback_error.__traceback__)

            if error is not None and not self.is_canceled:
                raise error.with_traceback(error.__traceback__)
