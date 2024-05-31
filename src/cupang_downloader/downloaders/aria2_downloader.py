import os
import socket
import subprocess
import time
import xmlrpc.client
from functools import lru_cache
from pathlib import Path
from threading import Event, Lock

from .._default import default_cacert
from .base import DownloaderBase, DownloaderSubprocessMixin

ARIA2_LOCK = Lock()


class Aria2Error(Exception):
    pass


def _is_port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _get_ttl_hash(seconds: int = 60):
    return round(time.time() / seconds)


class Aria2Downloader(DownloaderSubprocessMixin, DownloaderBase):
    """Aria2Downloader uses `aria2c` to download files."""

    def __init__(
        self,
        aria2c_bin: str | Path = None,
        max_download: int = 999,
        aria2_token: str = "A",
        cancel_event: Event = None,
    ) -> None:
        """
        Args:
            aria2c_bin (str, optional): Absolute path to the `aria2c` binary.
                If None then use system `aria2c`. Defaults to None.
            max_download (int, optional): Maximum number of concurrent downloads. Defaults to 999.
            aria2_token (str, optional): Token for Aria2 RPC. Defaults to "A".
            cancel_event (Event, optional): Event to signal download cancellation. Defaults to None.

        Raises:
            BinaryNotFoundError: If the `aria2c` binary is not found.
        """
        self.bin = self.check_bin(aria2c_bin or ("aria2c" if os.name != "nt" else "aria2c.exe"))
        self.max_download = max_download
        self._running = None
        self.aria2 = None
        self.aria2_secret = aria2_token
        self.aria2_token = f"token:{self.aria2_secret}"
        self.aria2_lock = ARIA2_LOCK
        super().__init__(cancel_event)

    def __pre_download__(self):
        port: int = next((i for i in range(6800, 7001) if _is_port_available(i)), None)

        if self._running is None:
            cmd = [
                str(self.bin),
                "--ca-certificate",
                str(default_cacert),
                "--file-allocation",
                "none",
                "--enable-rpc",
                "--rpc-secret",
                str(self.aria2_secret),
                "--rpc-listen-port",
                str(port),
                "--rpc-allow-origin-all",
                "--max-concurrent-downloads",
                str(self.max_download),
            ]
            if os.name == "nt":
                cmd = " ".join(cmd)
            self._running = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        self.aria2 = xmlrpc.client.ServerProxy(f"http://localhost:{port}/rpc")

    def __post_download__(self):
        if self._running is not None:
            self.popen_terminate(self._running, raise_nonzero_return=False)
            self._running = None
        self.aria2 = None

    @lru_cache()
    def _aria_tell_status(self, gid: str, *key, ttl_hash=None):
        del ttl_hash
        return self.aria2.aria2.tellStatus(self.aria2_token, gid, [*key])

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

        try:
            with self.aria2_lock:
                gid = self.aria2.aria2.addUri(
                    self.aria2_token,
                    [job.url],
                    {
                        "dir": str(job.out.parent),
                        "out": job.out.name,
                        "allow-overwrite": "true",
                        "headers": [f"{k}: {v}" for k, v in {**job.headers}.items()],
                    },
                )
            while not self.is_canceled:
                with self.aria2_lock:
                    try:
                        status = self._aria_tell_status(
                            gid, "status", "completedLength", "errorMessage", ttl_hash=_get_ttl_hash(1)
                        )
                    except (BaseException, Exception):
                        continue

                if status.get("status", None) != "active":
                    break

                downloaded = int(status.get("completedLength", 0))
                self._handle_progress(progress_callback, job, total, downloaded)

        finally:
            try:
                with self.aria2_lock:
                    if status.get("status", None) == "active":
                        self.aria2.aria2.remove(self.aria2_token, gid)
                    self.aria2.aria2.removeDownloadResult(self.aria2_token, gid)
            except (BaseException, Exception):
                pass
            job.out.with_name(job.out.name + ".aria2").unlink(missing_ok=True)
            if status and status.get("status", None) == "error":
                raise Aria2Error(status.get("errorMessage", "There is an error in Aria2 but unknown"))
