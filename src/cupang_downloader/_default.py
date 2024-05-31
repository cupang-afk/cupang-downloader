import ssl
from pathlib import Path

import certifi

default_headers = {"User-Agent": "CupangDownloader/0.1.0"}
default_cacert = Path(certifi.where()).absolute()
default_urllib_context = ssl.create_default_context(cafile=str(default_cacert))
