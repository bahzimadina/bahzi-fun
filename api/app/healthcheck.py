"""Health check container (dipakai HEALTHCHECK di Dockerfile).

Dijalankan di dalam image: `python /srv/app/healthcheck.py`
Keluar dengan kode 0 bila /health membalas HTTP 200, selain itu kode 1.
"""

from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request

URL = os.getenv("HEALTHCHECK_URL", "http://127.0.0.1:8000/health")
TIMEOUT = float(os.getenv("HEALTHCHECK_TIMEOUT", "4"))


def main() -> int:
    try:
        with urllib.request.urlopen(URL, timeout=TIMEOUT) as response:
            ok = response.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
