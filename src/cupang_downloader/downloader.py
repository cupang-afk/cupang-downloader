import io
import shutil
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from types import TracebackType
from typing import IO, Any, Callable, TypeAlias, TypeVar

from ._default import default_headers
from ._logger import log
from .downloaders.base import (
    DownloadedInt,
    DownloaderBase,
    ExtraDict,
    TotalInt,
)
from .error import DownloadError
from .job import DownloadJob
from .utils import read_in_chunk, remove_dir, remove_suffix, rename_path, temppath

T = TypeVar("T")


_StartCallback: TypeAlias = Callable[[DownloadJob], None]
_FinishCallback: TypeAlias = Callable[[DownloadJob], None]
_ProgressCallback: TypeAlias = Callable[[DownloadJob, TotalInt, DownloadedInt, ExtraDict], None | Any]
_CancelCallback: TypeAlias = Callable[[DownloadJob], None]
_ErrorCallback: TypeAlias = Callable[[DownloadJob, tuple[type[BaseException], Exception, TracebackType]], None]


def filesize(
    size: float,
    base: float = 1024,
    decimal: int = 2,
    units: list[str] = [" bytes", "KB", "MB", "GB", "TB", "PB", "EB"],
):
    """Returns a human readable string representation of bytes"""
    return f"{size:,.{decimal}f}{units[0]}" if size < base else filesize(size / base, base, decimal, units[1:])


# default callback
_callback_lock = Lock()


def _on_start(j: DownloadJob):
    with _callback_lock:
        print(f"\r\033[KDownloading {j.progress_name}", flush=True)


def _on_finish(j: DownloadJob):
    with _callback_lock:
        print(f"\r\033[KFinished download {j.progress_name}", flush=True)


def _on_progress(j: DownloadJob, t: int, d: int, **extra):
    with _callback_lock:
        print(f"\r\033[K{j.progress_name}: {filesize(t)}/{filesize(d)}", end="", flush=True)


def _on_cancel(j: DownloadJob):
    with _callback_lock:
        print(f"\r\033[KCanceled download {j.progress_name}", flush=True)


def _on_error(j: DownloadJob, err: tuple[type[BaseException], Exception, TracebackType]):
    with _callback_lock:
        print(
            f"\r\033[KError download {j.progress_name}",
            "\r\033[K" + "".join(traceback.format_exception(*err)),
            flush=True,
        )


class Downloader:
    """The Downloader"""

    def __init__(self, downloader: DownloaderBase):
        """
        Args:
            downloader (DownloaderBase): The downloader to be used.
        """
        if not isinstance(downloader, DownloaderBase):
            raise TypeError(f"{downloader} is not a subclass of DownloaderBase")
        self._downloader = downloader

    def cancel(self):
        """
        Cancel the ongoing download.
        """
        self._downloader.cancel_event.set()

    def reset_cancel(self):
        """
        Reset the cancellation event.
        """
        self._downloader.cancel_event.clear()

    def _handle_parent_path(self, path: Path):
        if not isinstance(path, Path):
            return
        if not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)

    def _handle_out(self, path: T, overwrite: bool) -> T:
        log.debug("Handle out")
        if not isinstance(path, Path):
            return path

        if path.exists() and not overwrite:
            log.debug(f"{path} is exists, but overwrite is False renaming")
            new_path = rename_path(path)
            log.debug(f"Rename {path} to {new_path}")
            path = new_path
        self._handle_parent_path(path)
        return path

    def _handle_headers(self, headers: dict[str, str]):
        return {**default_headers, **headers} if isinstance(headers, dict) else default_headers.copy()

    def _handle_callback(self, callback: Callable, *args, **kwargs):
        log.debug("Handle callback")
        if not callable(callback):
            log.debug(f"Cannot handle callback because {callback} is not callable")
            return
        log.debug(f"Running callback: {callback} with args: ({*args, *kwargs,})")
        return callback(*args, **kwargs)

    def _handle_result(self, result: Path, out: IO[bytes] | Path | None):
        if result is None:
            return

        if out is None:
            log.debug("out is None, writing to io.BytesIO()")
            out = io.BytesIO()
            with result.open("rb") as r:
                for chunk in read_in_chunk(r):
                    out.write(chunk)
        else:
            if isinstance(out, Path):
                log.debug(f"out is {out}, cleaning up and rename {result}")
                remove_dir(out.absolute())
                out = Path(shutil.copy(result.absolute(), out.absolute()))
                remove_dir(result.absolute())
            else:
                log.debug(f"out is writeable object {out}, write to it")
                with result.open("rb") as r:
                    for chunk in read_in_chunk(r):
                        out.write(chunk)

        remove_dir(result.absolute())
        return out

    def _dl(
        self,
        job: DownloadJob,
        _tmp: Path,
        *,
        on_start: _StartCallback = None,
        on_finish: _FinishCallback = None,
        on_progress: _ProgressCallback = None,
        on_cancel: _CancelCallback = None,
        on_error: _ErrorCallback = None,
        _with_pre: bool = True,
        _with_post: bool = True,
    ) -> Path | None:
        self._handle_parent_path(_tmp)
        tmp_job = job.copy_with_new_value(out=_tmp)

        try:
            if _with_pre:
                self._downloader.__pre_download__()

            self._handle_callback(on_start, tmp_job)

            # download
            self._downloader.download(tmp_job, on_progress)

            if self._downloader.is_canceled:
                self._handle_callback(on_cancel, tmp_job)
                return
            else:
                self._handle_callback(on_finish, tmp_job)
                return _tmp

        except (BaseException, Exception, KeyboardInterrupt) as e:
            # Treat KeyboardInterrupt as cancel when is_cancelled is False (happens on single download)
            if isinstance(e, KeyboardInterrupt) and not self._downloader.is_canceled:
                self._handle_callback(on_cancel, tmp_job)
                return

            if callable(on_error):
                self._handle_callback(on_error, tmp_job, (type(e), e, e.__traceback__))
                return
            else:
                raise DownloadError(f"Something wrong while downloading {tmp_job.progress_name}") from e
        finally:
            if _with_post:
                self._downloader.__post_download__()

    def dl(
        self,
        job: DownloadJob,
        *,
        overwrite=True,
        on_start: _StartCallback = None,
        on_finish: _FinishCallback = None,
        on_progress: _ProgressCallback = None,
        on_cancel: _CancelCallback = None,
        on_error: _ErrorCallback = None,
    ) -> Path | IO[bytes] | None:
        """
        Download a file.

        Args:
            job (DownloadJob): The download job.
            overwrite (bool, optional): Whether to allow existing files to be overwritten. Defaults to True.
            on_start (_StartCallback, optional): Callback for when the download starts. Defaults to None.
            on_finish (_FinishCallback, optional): Callback for when the download finishes. Defaults to None.
            on_progress (_ProgressCallback, optional): Callback for download progress updates. Defaults to None.
            on_cancel (_CancelCallback, optional): Callback for when the download is cancelled. Defaults to None.
            on_error (_ErrorCallback, optional): Callback for when an error occurs. Defaults to None.

        Returns:
            Path | IO[bytes] | None: The path to the downloaded file,
                or the downloaded content if no output path is specified,
                or None if download is fail or canceled.

        Raises:
            DownloadError: If no on_error callback is provided, this error is raised with a
                message indicating an issue occurred during the download.

        Notes:
            - If overwrite is False then job.out will be renamed to non-exists Path (only when job.out is a Path).
            - If a callback (on_start, on_finish, on_progress, etc.) is None, the default callback will be used.
              If you do not want to use a callback, set it to False.
        """
        job = job.copy_with_new_value(
            out=self._handle_out(job.out, overwrite), headers=self._handle_headers(job.headers)
        )
        if isinstance(job.out, Path):
            tmp_dir = job.out.parent
            tmp_prefix, _ = remove_suffix(job.out)
        else:
            tmp_dir = None
            tmp_prefix = "dltemp_"
        with temppath(dir=tmp_dir, prefix=tmp_prefix) as tmp:
            log.debug(f"set tmp download file of {job.url} to {tmp}")
            result = self._dl(
                job,
                tmp,
                on_start=_on_start if on_start is None else on_start,
                on_finish=_on_finish if on_finish is None else on_finish,
                on_progress=_on_progress if on_progress is None else on_progress,
                on_cancel=_on_cancel if on_cancel is None else on_cancel,
                on_error=_on_error if on_error is None else on_error,
            )
            return self._handle_result(result, job.out)

    def batch_dl(
        self,
        jobs: list[DownloadJob],
        *,
        overwrite: bool = True,
        max_download: int = 5,
        on_start: _StartCallback = None,
        on_finish: _FinishCallback = None,
        on_progress: _ProgressCallback = None,
        on_cancel: _CancelCallback = None,
        on_error: _ErrorCallback = None,
    ) -> tuple[list[Path | IO[bytes] | None], list[BaseException | None]]:
        """
        Download multiple files concurrently.

        Args:
            jobs (list[DownloadJob]): List of download jobs.
            overwrite (bool, optional): Whether to allow existing files to be overwritten. Defaults to True.
            max_download (int, optional): Maximum number of concurrent downloads. Defaults to 5.
            on_start (_StartCallback, optional): Callback for when the download starts. Defaults to None.
            on_finish (_FinishCallback, optional): Callback for when the download finishes. Defaults to None.
            on_progress (_ProgressCallback, optional): Callback for download progress updates. Defaults to None.
            on_cancel (_CancelCallback, optional): Callback for when the download is cancelled. Defaults to None.
            on_error (_ErrorCallback, optional): Callback for when an error occurs. Defaults to None.

        Returns:
            tuple[list[Path | IO[bytes] | None], list[BaseException | None]]:
                A tuple containing two lists:
                - The first list contains the paths to the downloaded files,
                  or the downloaded content if no output path is specified,
                  or None if the download failed or was cancelled.
                - The second list contains any exceptions that were raised during the downloads,
                  or None if no exceptions were raised.

        Notes:
            - This function will block your thread and wait until it finished.
            - If overwrite is False then job.out will be renamed to non-exists Path (only when job.out is a Path).
            - If a callback (on_start, on_finish, on_progress, etc.) is None, the default callback will be used.
              If you do not want to use a callback, set it to False.
            - The returned lists are guaranteed to be in the same order as the jobs.
        """

        def _dl_worker(job: DownloadJob):
            job = job.copy_with_new_value(
                out=self._handle_out(job.out, overwrite),
                headers=self._handle_headers(job.headers),
            )
            if isinstance(job.out, Path):
                tmp_dir = job.out.parent
                tmp_prefix, _ = remove_suffix(job.out)
            else:
                tmp_dir = None
                tmp_prefix = "dltemp_"
            with temppath(dir=tmp_dir, prefix=tmp_prefix) as tmp:
                result = self._dl(
                    job,
                    tmp,
                    on_start=_on_start if on_start is None else on_start,
                    on_finish=_on_finish if on_finish is None else on_finish,
                    on_progress=on_progress,  # no default progress_callback for batch download
                    on_cancel=_on_cancel if on_cancel is None else on_cancel,
                    on_error=_on_error if on_error is None else on_error,
                    _with_pre=False,
                    _with_post=False,
                )
                return self._handle_result(result, job.out)

        try:
            self._downloader.__pre_download__()
            with ThreadPoolExecutor(max_download) as t:
                download_jobs = [t.submit(_dl_worker, job) for job in jobs]

                # wait
                try:
                    while not all([j.done() for j in download_jobs]):
                        time.sleep(1)
                except KeyboardInterrupt:
                    self.cancel()
                finally:
                    t.shutdown(wait=True, cancel_futures=True)
                    self.reset_cancel()
                res = [r.result() if (not r.cancelled() and r.exception() is None) else None for r in download_jobs]
                exc = [r.exception() if not r.cancelled() else None for r in download_jobs]
                return res, exc
        finally:
            self._downloader.__post_download__()
