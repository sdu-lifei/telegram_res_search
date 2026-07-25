#!/usr/bin/env python3
"""Submit the canonical PanSou pages after a deployment or content update."""

import json
import sys
from urllib.request import Request, urlopen

HOST = "panss.dpdns.org"
KEY = "936e19624328486fafd9e3e97e1f2b5c709c99597f3399a87db3a5872fed507b"
KEY_LOCATION = f"https://{HOST}/{KEY}.txt"


def main() -> int:
    urls = sys.argv[1:] or [
        f"https://{HOST}/",
        f"https://{HOST}/about",
        f"https://{HOST}/guides",
        f"https://{HOST}/guides/public-cloud-link-safety-checklist",
        f"https://{HOST}/guides/cloud-search-keyword-guide",
        f"https://{HOST}/guides/shared-files-organization-guide",
    ]
    payload = json.dumps({"host": HOST, "key": KEY, "keyLocation": KEY_LOCATION, "urlList": urls}).encode()
    request = Request("https://api.indexnow.org/indexnow", data=payload, headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
    with urlopen(request, timeout=30) as response:
        print(f"IndexNow accepted submission: HTTP {response.status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
