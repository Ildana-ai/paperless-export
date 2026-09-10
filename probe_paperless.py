#!/usr/bin/env python3
"""Phase L handshake probe for paperless-export.

Reads PAPERLESS_URL and PAPERLESS_TOKEN from the environment. Never a flag, never a URL.
Prints server version, API version, document count, custom fields and saved views.
Exits non-zero on anything short of 200 so a broken link halts the build.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

API_VERSION = "10"
TIMEOUT = 30


class ProbeError(Exception):
    pass


# The URL policy has exactly one implementation. Importing it here keeps the probe and the
# engine from drifting apart; paperless_export is stdlib-only until --format xlsx is asked for.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from paperless_export import ExportError, SameOriginRedirect, is_private_host  # noqa: E402


def check_url(raw: str, insecure: bool) -> str:
    parts = urllib.parse.urlsplit(raw)
    if parts.scheme not in ("http", "https"):
        raise ProbeError(f"URL scheme must be http or https, got {parts.scheme!r}")
    if parts.query or parts.fragment:
        raise ProbeError("refusing a URL carrying a query or fragment (tokens never ride in URLs)")
    if parts.scheme == "http" and not is_private_host(parts.hostname or ""):
        if not insecure:
            raise ProbeError(
                f"refusing plain http to {parts.hostname!r}: it is not a private address "
                "and does not resolve to one. Use https, or pass --insecure if you "
                "accept a cleartext token"
            )
        print(f"WARNING: plain http to public host {parts.hostname} (--insecure)", file=sys.stderr)
    elif parts.scheme == "http":
        print(f"note: plain http to private host {parts.hostname}", file=sys.stderr)
    return f"{parts.scheme}://{parts.netloc}{parts.path.rstrip('/')}"


def get(opener, base: str, path: str, token: str):
    req = urllib.request.Request(
        f"{base}{path}",
        headers={
            "Authorization": f"Token {token}",
            "Accept": f"application/json; version={API_VERSION}",
        },
    )
    try:
        with opener.open(req, timeout=TIMEOUT) as r:
            if r.status != 200:
                raise ProbeError(f"{path} returned HTTP {r.status}")
            # r.headers stays an HTTPMessage: the server sends these lowercase.
            return json.loads(r.read()), r.headers
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:200]
        raise ProbeError(f"{path} returned HTTP {e.code}: {detail}") from None
    except urllib.error.URLError as e:
        raise ProbeError(f"{path} unreachable: {e.reason}") from None


def main() -> int:
    insecure = "--insecure" in sys.argv
    url = os.environ.get("PAPERLESS_URL", "").strip()
    token = os.environ.get("PAPERLESS_TOKEN", "").strip()
    if not url or not token:
        print("PAPERLESS_URL and PAPERLESS_TOKEN must be set in the environment", file=sys.stderr)
        return 2

    try:
        base = check_url(url, insecure)
        opener = urllib.request.build_opener(SameOriginRedirect)

        docs, headers = get(opener, base, "/api/documents/?page_size=1", token)
        fields, _ = get(opener, base, "/api/custom_fields/?page_size=1000", token)
        views, _ = get(opener, base, "/api/saved_views/?page_size=1000", token)

        print(f"server        {headers.get('X-Version', '(no X-Version header)')}")
        print(f"api version   {headers.get('X-Api-Version', '(no X-Api-Version header)')} (requested {API_VERSION})")
        print(f"url           {base}")
        print(f"documents     {docs['count']}")

        print(f"custom fields {fields['count']}")
        for f in fields["results"]:
            extra = ""
            if f.get("data_type") == "select":
                opts = (f.get("extra_data") or {}).get("select_options") or []
                extra = f"  [{len(opts)} options]"
            print(f"  {f['id']:>3}  {f['data_type']:<12} {f['name']}{extra}")

        print(f"saved views   {views['count']}")
        for v in views["results"]:
            cols = ", ".join(v.get("display_fields") or []) or "(default columns)"
            sort = ("-" if v.get("sort_reverse") else "") + str(v.get("sort_field"))
            print(f"  {v['id']:>3}  {v['name']}  sort={sort}  rules={len(v.get('filter_rules') or [])}  cols={cols}")

    except (ProbeError, ExportError) as e:
        print(f"PROBE FAILED: {e}", file=sys.stderr)
        return 1

    print("\nprobe OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
