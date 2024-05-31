class BinaryNotFoundError(Exception):
    """
    Exception raised when a required binary is not found in the system PATH.

    Attributes:
        bin (str): The name of the binary that was not found.
    """

    def __init__(self, bin: str):
        self.bin = bin

    def __str__(self):
        return "%s is not found anywhere in PATH" % (self.bin)


class CallbackNonZeroReturnError(Exception):
    """
    Exception raised when a callback returns a non-zero value.
    """

    pass


class DownloadError(Exception):
    """
    Exception raised for errors occurring during the download process.
    """

    pass
