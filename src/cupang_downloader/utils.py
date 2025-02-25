import random
import shutil
import stat
import string
import tempfile
import time
import urllib.request
from contextlib import contextmanager
from http.client import HTTPResponse
from pathlib import Path
from typing import IO, TypeAlias, cast

from ._default import default_headers, default_urllib_context

_StrOrPath: TypeAlias = str | Path


def read_in_chunk(o: IO[bytes], chunk_size: int = 8192):
    while True:
        chunk = o.read(chunk_size)
        if not chunk:
            break
        yield chunk


def safe_delete(path: Path, max_retries: int = 10):
    """
    Safely delete a file or directory with multiple retry attempts.

    Args:
        path (str or Path): Path to file or directory to delete
        max_retries (int): Maximum number of retry attempts

    Raises:
        RuntimeError: If deletion fails after all retry attempts
    """
    if not path.exists():
        return

    for attempt in range(max_retries):
        try:
            if path.is_file():
                path.unlink(missing_ok=True)
            else:
                shutil.rmtree(path.absolute())
            return  # Successful deletion

        except (PermissionError, OSError) as e:
            if attempt == max_retries - 1:
                raise RuntimeError(f"Failed to delete {path} after {max_retries} attempts") from e

            wait_time = 1 * (1.3**attempt) * (random.random() * 0.1)
            time.sleep(wait_time)


def remove_dir(path: Path, tries: int = 15):
    if not path.exists():
        return
    if path.is_dir():
        for _ in path.rglob("*"):
            _.chmod(stat.S_IWRITE)
    else:
        path.chmod(stat.S_IWRITE)

    # ensure dir are deleted
    for _ in range(tries):
        try:
            safe_delete(path)
        except Exception:
            pass
        time.sleep(1)


def remove_suffix(path: Path):
    stem = path.stem.replace("".join(path.suffixes), "")
    suffixes = path.suffixes
    return stem, suffixes


def rename_path(
    path: Path,
    name_format: str = "{stem} ({number})",
):
    if not path.exists():
        return path

    stem, suffixes = remove_suffix(path)

    number = 1
    while True:
        tmp = path.with_name(name_format.format(stem=stem, number=number)).with_suffix("".join(suffixes))
        if not tmp.exists():
            return tmp
        number += 1


@contextmanager
def temppath(
    dir: _StrOrPath = None,
    prefix: str = None,
    suffix: str = None,
    delete: bool = True,
):
    """
    Context manager for creating temporary files or directories.

    Args:
        dir (_StrOrPath, optional): The directory where the temporary file or directory will be created.
            If None, the system default temporary directory will be used. Defaults to None.
        prefix (str, optional): Prefix to be added to the temporary file or directory name. Defaults to None.
        suffix (str, optional): Suffix to be added to the temporary file or directory name. Defaults to None.
        delete (bool, optional): If True, the temporary file or directory will be deleted after use. Defaults to True.

    Yields:
        (Path): The path to the created temporary file or directory.
    """
    name_template = "{prefix}{randomname}{suffix}"

    dir = Path(dir or tempfile.gettempdir()).absolute()
    while True:
        tmp = dir / name_template.format(
            prefix=prefix or "tmp",
            randomname="".join(
                random.choices(string.ascii_letters, k=10),
            ),
            suffix=suffix or "",
        )
        if not tmp.exists():
            break

    try:
        yield tmp
    finally:
        if delete:
            safe_delete(tmp)


@contextmanager
def request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] = None,
    **kwargs,
):
    """
    A wrapper for `urllib.request.urlopen` module with common configurations.

    Args:
        url (str): The URL to send the request to.
        method (str, optional): The HTTP method to use, e.g., "GET" or "POST". Defaults to "GET".
        headers (dict[str, str], optional): A dictionary of HTTP headers to send with the request. Defaults to None.

    Yields:
        (HTTPResponse): The response object received after making the request.
    """
    if headers is None:
        headers = default_headers.copy()
    else:
        headers = {**default_headers, **headers}

    req = urllib.request.Request(url, method=method, headers=headers, **kwargs)
    with urllib.request.urlopen(req, context=default_urllib_context) as res:
        res = cast(HTTPResponse, res)
        yield res
    return res
