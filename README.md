
a download wrapper with callback

## Documentation

Documentation are located [here](https://cupang-afk.github.io/cupang-downloader/)

## Install

```
pip install git+https://github.com/cupang-afk/cupang-downloader
```

## Usage

```python
from cupang_downloader import Downloader, DownloadJob
from cupang_downloader.downloaders.curl_downloader import CurlDownloader

d = Downloader(CurlDownloader())
job = DownloadJob(url="https://link.testfile.org/bNYZFw", out="10MB.mp4") 

d.dl(job=job)
```

## Supported Downloaders

- `aria2_downloader` Uses [`aria2c`](https://aria2.github.io/) to download a file 
- `curl_downloader` Uses [`curl`](https://curl.se/) to download a file
- `pycurl_downloader` Uses [`pycurl`](http://pycurl.io/) Python module to download a file _(refer to their website for installation instructions)_
- `requests_downloader` Uses [`requests`](https://requests.readthedocs.io/) Python module to download a file
- `urllib_downloader` Uses built-in [`urllib.request`](https://docs.python.org/3/library/urllib.request.html) Python module to download file
- `wget_downloader` Uses [`wget`](https://www.gnu.org/software/wget/) to download file 

These downloaders are cross-platform, provided the necessary requirements are installed.

## Adding Custom Downloaders

If you want to use a downloader not listed above, you can add it yourself.

For example, here's how to create a Git downloader

```python
"""Example how to create a git downloader using `git` command"""

import os
import re
import stat
import subprocess
from pathlib import Path
from threading import Event

from cupang_downloader import DownloaderBase, DownloaderSubprocessMixin


class GitDownloader(DownloaderSubprocessMixin, DownloaderBase):
    """GitDownloader uses `git` to download repositories."""

    def __init__(self, git_bin: str | Path = None, cancel_event: Event = None) -> None:
        """
        Args:
            git_bin (str | Path, optional): Absolute path to the `git` binary.
                If None then use system `git`. Defaults to None..
            cancel_event (Event, optional): Event to signal download cancellation. Defaults to None.
        """
        self.bin = self.check_bin(git_bin or ("git" if os.name != "nt" else "git.exe"))
        self.cmd = [str(self.bin), "clone", "--progress"]
        self.git_pattern = re.compile(r"\((\d+)/(\d+)\)")  # capture something like (0/177) in clone progress
        super().__init__(cancel_event, None)

    def _set_permission(self, dir: Path):
        if not dir.exists():
            return
        dir.chmod(stat.S_IWRITE)
        for file in dir.rglob("*"):
            file.chmod(stat.S_IWRITE)

    def download(
        self,
        job,
        progress_callback,
    ) -> None:
        try:
            # we run git command using .popen_wrapper
            with self.popen_wrapper(
                self.cmd + [job.url, str(job.out.absolute())],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=None,
                universal_newlines=True,
                bufsize=1,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            ) as p:
                while p.poll() is None and not self.is_canceled:
                    line = p.stdout.readline()
                    line_lower = line.lower()
                    if not line:
                        break

                    # read stdout and use some of its status as progress tracking
                    #
                    if "done" in line_lower:
                        # if line has "done" then the process is done
                        continue
                    #
                    # the cloning process status
                    if "counting objects" in line_lower:
                        git_status = "Counting"
                    elif "compressing objects" in line_lower:
                        git_status = "Compressing"
                    elif "receiving objects" in line_lower:
                        git_status = "Receiving"
                    elif "resolving deltas" in line_lower:
                        git_status = "Resolving"
                    elif "updating files" in line_lower:
                        git_status = "Updating"

                    # failsafe if there any extra step in cloning progress (usually there isn't)
                    else:
                        git_status = "?"

                    # find pattern of object being cloned
                    matches = self.git_pattern.search(line)

                    # the clone is still running but we don't have anything to be report
                    # so we continue
                    if not matches:
                        continue

                    # call the progress_callback
                    total = int(matches.group(2))
                    downloaded = int(matches.group(1))
                    speed = (line.split(",")[1:] + [""])[0].strip()
                    self._handle_progress(
                        progress_callback,
                        job,
                        total,
                        downloaded,
                        # extra progress status to be send to the progress_callback
                        # we can utilize this
                        git_status=git_status,
                        git_speed=speed,
                    )
        finally:
            # to obey the shutil.move
            # we need to add write permission to the cloned folder
            # sometime it fail to do so when we leave the permission as is
            self._set_permission(job.out)
```

### Usage Example for GitDownloader

```python
from pathlib import Path

from cupang_downloader import CupangDownloader, DownloadJob

# git progress callback
def git_progress(j: DownloadJob, t: int, d: int, **extra):
    print(f"\r\033[K{j.progress_name}: {t}/{d} {extra['git_status']} {extra['git_speed']}", end="", flush=True)


b = CupangDownloader(GitDownloader())
b.dl(
    DownloadJob("https://GITURL", Path("SOMEPROJECT")),
    on_progress=git_progress, # add git progress callback
)
```


## Callback

You can pass custom callback functions to the `.dl()` function, including:

- `on_start`
- `on_finish`
- `on_progress`
- `on_cancel`
- `on_error`

### `on_start`, `on_finish`, `on_cancel` 

These callbacks receive one argument: the `DownloadJob` object.

```python
def on_start(job: DownloadJob):
    print("Starting", job.progress_name)
```

### `on_error` 

This callback receives two arguments: the `DownloadJob` object and a tuple containing the exception type, exception instance, and traceback.

```python
def on_error(job: DownloadJob, error: tuple[type[BaseException], Exception, TracebackType]):
    print("Something went wrong", error[1])
```

### `on_progress` 
 
This callback receives four arguments: the `DownloadJob` object, total file size (`int`), downloaded file size (`int`), and additional keyword arguments (`extra`), which depend on the downloader.


```python
def on_progress(job: DownloadJob, total: int, downloaded: int, **extra):
    print("Downloading", job.progress_name, f"{total}/{downloaded}")
```

> [!WARNING]
> `on_progress` callback should return `None` otherwise it will raise `CallbackNonZeroReturnError`


## TODO

- [ ] fixing stuff