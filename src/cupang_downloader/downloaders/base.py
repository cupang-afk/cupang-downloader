import os
import shutil
import signal
import subprocess
from abc import ABCMeta, abstractmethod
from contextlib import contextmanager
from logging import Logger
from pathlib import Path
from threading import Event
from typing import Any, Callable, TypeAlias

from runtime_final import final

from .._logger import log
from ..error import BinaryNotFoundError, CallbackNonZeroReturnError
from ..job import DownloadJob
from ..utils import request

TotalInt: TypeAlias = int
DownloadedInt: TypeAlias = int
ExtraDict: TypeAlias = dict[str, Any]


class DownloaderBase(metaclass=ABCMeta):
    """
    A base class for downloader classes.

    Notes:
        - Subclasses must implement their own `.download()` method.
        - If you define an `.__init__()` method in a subclass, you must call `super().__init__()`.
        - The `.__pre_download()` and `.__post_download()` methods are optional
          and only needed if preparation or cleanup is required for your downloader.

    Tip: Some tips
        - Use the `._handle_progress()` method for calling `progress_callback`.
        - The `._log` attribute is available for verbose logging, although its use is optional.
    """

    def __init__(self, cancel_event: Event = None, chunk_size: int = None) -> None:
        """
        Args:
            cancel_event (Event, optional): Event to signal download cancellation. Defaults to None.
            chunk_size (int, optional): Size of each chunk to be downloaded. Defaults to None.
        """
        self.cancel_event = cancel_event or Event()
        self.chunk_size = chunk_size or 8192

    @final
    @property
    def _log(self) -> Logger:
        """A Logger instance of this module"""
        return log

    @final
    @property
    def is_canceled(self) -> bool:
        """Check if `.cancel_event` is set"""
        return self.cancel_event.is_set()

    @final
    @property
    def request(self):
        """
        A request wrapper

        See Also:
            - [cupang_downloader.utils.request][]
        """
        return request

    @final
    def _handle_progress(
        self,
        progress_callback,
        job: DownloadJob,
        total: TotalInt,
        downloaded: DownloadedInt,
        **extra,
    ) -> None:
        """Handle progress callback"""
        if not callable(progress_callback):
            return
        if progress_callback(job, total, downloaded, **extra) is not None:
            raise CallbackNonZeroReturnError

    def __pre_download__(self) -> None:
        """Prepare downloader"""
        ...

    def __post_download__(self) -> None:
        """Cleanup downloader"""
        ...

    @abstractmethod
    def download(
        self,
        job: DownloadJob,
        progress_callback: Callable[[DownloadJob, TotalInt, DownloadedInt, ExtraDict], None | Any],
    ) -> None:
        """
        Execute the download process for a given job.

        Args:
            job (DownloadJob): The download job containing details such as URL, headers, output destination, etc.
            progress_callback (Callable[[DownloadJob, TotalInt, DownloadedInt, ExtraDict], None | Any]):
                A callback function to handle progress updates.

        Raises:
            BaseException: Any exceptions related to the download process will be propagated as needed.
        """


class DownloaderSubprocessMixin:
    """A Mixin class that can help if the downloader utilize external command."""

    @final
    def check_bin(self, bin: str | Path) -> Path:
        """
        Check if the binary is available in the system.

        Args:
            bin (str | Path): The name or absolute path of the binary to check.

        Raises:
            BinaryNotFoundError: If the binary is not found in PATH.
            FileNotFoundError: If the binary is an absolute path and file not exists.

        Returns:
            Path: The absolute path of the binary if it is found.
        """
        bin = bin if isinstance(bin, Path) else Path(bin)
        if bin.is_absolute():
            if not bin.is_file():
                raise FileNotFoundError(str(bin))
            return bin.absolute()
        else:
            bin_from_path = shutil.which(str(bin))
            if not bin_from_path:
                raise BinaryNotFoundError(str(bin))
            return Path(bin_from_path).absolute()

    @contextmanager
    def popen_wrapper(self, command: list[str], *, raise_nonzero_return=False, **popen_kwargs):
        """
        A context manager for subprocess.Popen.

        This wrapper will try to terminate the process when we leave the `with` block.

        by default `stdout`, `stderr`, and `stdin` are filled with subprocess.PIPE.
        if you need to disable some, you should pass it as None

        Args:
            command (list[str]): The command to execute.
            raise_nonzero_return (bool, optional): Whether to raise an exception
                if the command returns a non-zero exit code. Defaults to False.

        Raises:
            subprocess.CalledProcessError: If the process returns a non-zero exit code
                and raise_nonzero_return is True.

        Yields:
            (subprocess.Popen): The Popen object representing the running process.
        """

        if "stdout" not in popen_kwargs:
            popen_kwargs["stdout"] = subprocess.PIPE
        if "stderr" not in popen_kwargs:
            popen_kwargs["stderr"] = subprocess.PIPE
        if "stdin" not in popen_kwargs:
            popen_kwargs["stdin"] = subprocess.PIPE

        try:
            p = subprocess.Popen(command, **popen_kwargs)
            yield p
        finally:
            self.popen_terminate(p, raise_nonzero_return)

    def popen_terminate(self, p: subprocess.Popen, raise_nonzero_return=True):
        """
        Terminate a subprocess.

        Args:
            p (subprocess.Popen): The subprocess to terminate.
            raise_nonzero_return (bool, optional): Whether to raise an exception
                if the process returns a non-zero exit code. Defaults to True.

        Raises:
            subprocess.CalledProcessError: If the process returns a non-zero exit code
                and raise_nonzero_return is True.
        """
        stdout = None
        stderr = None
        while p.poll() is None:
            try:
                stdout, stderr = p.communicate(timeout=15)
            except subprocess.TimeoutExpired:
                if os.name == "nt":
                    p.send_signal(signal.CTRL_BREAK_EVENT)
                    p.send_signal(signal.CTRL_C_EVENT)
                p.kill()
        if p.returncode != 0 and raise_nonzero_return:
            raise subprocess.CalledProcessError(returncode=p.returncode, cmd=p.args, output=stdout, stderr=stderr)
