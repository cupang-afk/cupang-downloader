"""Example of how to use download callback using `rich.progress`"""

from threading import Lock

from cupang_downloader import Downloader, DownloadJob
from cupang_downloader.downloaders.curl_downloader import CurlDownloader
from rich.progress import Progress, SpinnerColumn, TaskID, TransferSpeedColumn
from rich.traceback import Traceback

c = Downloader(CurlDownloader())  # any downloader

with Progress(SpinnerColumn(), *Progress.get_default_columns(), TransferSpeedColumn()) as pp:
    # save any running progress bar
    # so we can take it in our callback function
    progresses: dict[str, TaskID] = {}
    progresses_lock = Lock()

    # create an unique id
    # we utilize the DownloadJob object and retrive its memory id
    # and convert it to hex
    def create_unique_id(o):
        return hex(id(o))

    # remove the progress bar when download is finished, canceled, or error
    def remove_bar(k: str):
        pp.update(progresses[k], visible=False)
        pp.remove_task(progresses[k])
        # using lock we can now remove the progress from dictionary
        # by using lock, we ensure that only one thread can edit the dictionary
        with progresses_lock:
            del progresses[k]

    def _on_start(j: DownloadJob):
        k = create_unique_id(j)
        # create new progress bar and save to progresses
        progresses[k] = pp.add_task(description=j.progress_name, total=None, visible=False)

    def _on_finish(j: DownloadJob):
        pp.print("Finished", j.progress_name)
        k = create_unique_id(j)
        remove_bar(k)

    def _on_progress(j: DownloadJob, t: int, d: int, **extra):
        k = create_unique_id(j)
        # we set to None because rich.progress has pulse animation when total is None
        t = None if t == 0 else t
        pp.update(progresses[k], total=t, completed=d, visible=True)

    def _on_cancel(j: DownloadJob):
        pp.print("Canceled", j.progress_name)
        k = create_unique_id(j)
        remove_bar(k)

    def _on_error(j: DownloadJob, err):
        pp.print("Error while downloading", j.progress_name, Traceback(Traceback.extract(*err)))
        k = create_unique_id(j)
        remove_bar(k)

    # download
    result = c.dl(
        DownloadJob("https://link.testfile.org/aXCg7h", "out.mp4"),  # 11MB
        on_start=_on_start,
        on_finish=_on_finish,
        on_progress=_on_progress,
        on_cancel=_on_cancel,
        on_error=_on_error,
    )
