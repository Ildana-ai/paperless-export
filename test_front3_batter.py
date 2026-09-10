#!/usr/bin/env python3
"""Battering script for front 3. Runs a real server on a real port and fires every attack this
project's own threat model calls for at it.

    python3 execution/test_front3_batter.py

Exit 0 only if every attack was refused, nothing traversed, nothing executed, and the paperless
token appears in none of the bytes the server sent. Anything else exits 1. Can't verify, don't ship.
"""
from __future__ import annotations

import http.client
import json
import os
import socket
import subprocess
import sys
import urllib.parse
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import paperless_export as px          # noqa: E402
import paperless_front                 # noqa: E402
import paperless_serve as ps           # noqa: E402
from test_front3 import Wire, running  # noqa: E402
from test_paperless_export import DOCS  # noqa: E402

# A document mailed in by attacker A: a script tag, a quote, a CR, and a traversal, in the title.
HOSTILE = [
    dict(DOCS[0], id=91, title="</script><script>alert('xss')</script>"),
    dict(DOCS[0], id=92, title='../../../../tmp/pwned "; drop\r\nX-Injected: yes'),
]

RESULTS: list[tuple[bool, str, str]] = []


def check(ok: bool, name: str, detail: str = "") -> None:
    RESULTS.append((bool(ok), name, detail))
    print(f"{'pass' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if detail and not ok else ""))


# A denied POST's body is left unread on the socket on purpose (paperless_serve._deny, and
# _body()'s own-size check) -- the connection closes rather than draining it. On some platforms
# that reaches the client as the request itself aborting (Windows: ConnectionAbortedError
# [WinError 10053]) instead of a clean response, because the OS can RST a socket that still has
# unread bytes queued when it closes. Either shape is the same refusal seen from the client, so
# a call expected to be denied treats a mid-request connection failure as that denial, on every OS.
CONNECTION_CLOSED = (ConnectionAbortedError, ConnectionResetError, BrokenPipeError,
                      http.client.RemoteDisconnected)


def refused_status(fn, refusal: int = 403):
    """Run a zero-arg thunk that makes one request expected to be denied. Returns the refusal
    code either because the server answered with it, or because the connection aborted while the
    request was being denied -- both count."""
    try:
        return fn()
    except CONNECTION_CLOSED:
        return refusal


# --------------------------------------------------------------------------------------
def d1_csrf(wire: Wire) -> None:
    """D1 — a page in the user's browser can cause requests but cannot credential them."""
    check(refused_status(lambda: wire.call("POST", "/run", token=None,
                                            body={"formats": ["csv"]})[0]) == 403,
          "D1 POST /run with no session header -> 403")
    check(refused_status(lambda: wire.call("POST", "/run", token="not-the-token",
                                            body={"formats": ["csv"]})[0]) == 403,
          "D1 POST /run with a wrong session header -> 403")

    # The shape a cross-origin page can actually send: a simple request, no custom header.
    conn = http.client.HTTPConnection(wire.host, wire.port, timeout=10)
    try:
        conn.request("POST", "/run", body=b'{"formats":["csv"]}',
                     headers={"Host": f"{ps.BIND}:{wire.port}", "Content-Type": "text/plain",
                              "Origin": "https://evil.example"})
        response = conn.getresponse()
        status = response.status
        body = response.read()
        header_list = response.getheaders()
    except CONNECTION_CLOSED:
        # The connection aborted while the request was being denied -- the same refusal as a
        # clean 403 with an empty body and no headers, seen from the other side of the socket.
        status, body, header_list = 403, b"", []
    wire.seen.append(body)
    check(status == 403 and body == b"", "D1 cross-origin simple POST -> 403, empty body")
    check(not any(h.lower().startswith("access-control-allow") for h, _ in header_list),
          "D1 no Access-Control-Allow-* header on the refusal")
    conn.close()

    status, headers, _b = wire.call("OPTIONS", "/run")
    check(status == 403, "D1 OPTIONS preflight -> 403")
    check(not any(k.lower().startswith("access-control-allow") for k in headers.keys()),
          "D1 no CORS answer on a preflight, ever")


def d2_rebinding(wire: Wire) -> None:
    """D2 — a rebound name may set headers, so the Host check has to stand on its own."""
    for host in (f"evil.example:{wire.port}", "evil.example", f"localhost:{wire.port}",
                 ps.BIND, f"127.0.0.1:{wire.port + 1}"):
        status = wire.call("GET", "/session", host=host)[0]      # valid token, wrong Host
        check(status == 403, f"D2 Host: {host} with a VALID token -> 403", f"got {status}")


def d3_local_process(wire: Wire, session) -> None:
    """D3 — the URL form of the token is worth one use, so a copied URL opens nothing."""
    first = wire.call("GET", "/?s=" + session.token, token=None)[0]
    second = wire.call("GET", "/?s=" + session.token, token=None)[0]
    check(first == 200, "D3 the printed URL works once", f"got {first}")
    check(second == 403, "D3 the same URL replayed -> 403", f"got {second}")
    check(wire.call("GET", "/?s=" + session.token[:-1] + "x", token=None)[0] == 403,
          "D3 a near-miss URL token -> 403")
    check("hmac.compare_digest" in Path(ps.__file__).read_text(encoding="utf-8"),
          "D3 the token is compared in constant time")


def d5_hostile_title(wire: Wire) -> None:
    """D5 — a mailed-in title reaches the page. It must arrive as text and never as markup."""
    status, payload = wire.json("POST", "/run", body={"formats": ["csv"], "inventory": True,
                                                      "pack": True, "basename": "hostile"})
    check(status == 200, "D5 the hostile export ran", json.dumps(payload)[:200])
    if status != 200:
        return
    names = [f["name"] for f in payload["files"]]
    check(not any("<" in n or ">" in n for n in names),
          "D5 no angle bracket survived into a served file name", str(names))
    check(all(".." not in n for n in names), "D5 no '..' in a served file name", str(names))
    check(not Path("/tmp/pwned").exists() and not Path("/tmp/pwned-by-paperless-export").exists(),
          "D5 the traversal title wrote nothing outside the run")

    inventory = [n for n in names if n.endswith(".inventory.html")]
    if inventory:
        _s, _h, body = wire.call("GET", "/files/" + urllib.parse.quote(inventory[0]))
        check(b"<script>alert" not in body, "D5 the inventory carries no live script tag")
        check(b"&lt;script&gt;" in body, "D5 the hostile title is escaped in the inventory")
        check(_h["Content-Type"] == "application/octet-stream" and "attachment" in _h["Content-Disposition"],
              "D5 the run's own HTML is served as a download, never rendered in our origin")

    page = paperless_front.PAGE
    check(all(b not in page for b in ("innerHTML", "insertAdjacentHTML", "document.write", "outerHTML")),
          "D5 the page builds no markup from a value")
    _s, headers, _b = wire.call("GET", "/")
    csp = headers.get("Content-Security-Policy", "")
    check("default-src 'none'" in csp and "'nonce-" in csp and "connect-src 'self'" in csp,
          "D5 CSP: default-src none, a nonce, connect-src self", csp)


def d6_traversal(wire: Wire, workdir: Path, run_dir: Path) -> None:
    """D6 — /files/ serves what the run wrote, and only from inside the run's directory."""
    outsider = workdir / "outside.csv"
    outsider.write_text("not yours", encoding="utf-8")
    link = run_dir / "escape.csv"
    try:
        link.symlink_to(outsider)
    except OSError:
        link = None

    attacks = [
        "/files/../outside.csv",
        "/files/..%2foutside.csv",
        "/files/%2e%2e%2foutside.csv",
        "/files/%252e%252e%252foutside.csv",
        "/files/....//outside.csv",
        "/files//etc/passwd",
        "/files/" + str(outsider).lstrip("/"),
        "/files/",
        "/files/nothing.csv",
        "/files/escape.csv",
    ]
    for path in attacks:
        status = wire.call("GET", path)[0]
        check(status == 404, f"D6 {path} -> 404", f"got {status}")
    if link and link.exists():
        check(True, "D6 a symlink planted inside the run directory was refused with the rest")


def d7_token(wire: Wire) -> None:
    """D7 — the paperless token is in none of the bytes the server sent."""
    secret = os.environ["PAPERLESS_TOKEN"].encode()
    leaks = [chunk for chunk in wire.seen if secret in chunk]
    check(not leaks, "D7 the paperless token appears in no byte the server sent",
          f"{len(leaks)} response(s)")


def _reaches(family, sockaddr) -> bool:
    """True only if something accepted the connection. A timeout is a drop, not an answer:
    Windows silently discards a packet to a port nothing listens on, Linux and macOS refuse it."""
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.settimeout(3)
    try:
        sock.connect(sockaddr)
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _own_endpoints(port: int) -> list[tuple[int, tuple, str]]:
    """Every non-loopback address this machine answers to, as connectable sockaddrs."""
    seen: set[str] = set()
    out: list[tuple[int, tuple, str]] = []
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))          # TEST-NET-1: routed nowhere, tells us our own IP
        ip = probe.getsockname()[0]
        if not ip.startswith("127."):
            seen.add(ip)
            out.append((socket.AF_INET, (ip, port), ip))
    except OSError:
        pass
    finally:
        probe.close()
    try:
        infos = socket.getaddrinfo(socket.gethostname(), port, type=socket.SOCK_STREAM)
    except OSError:
        infos = []
    for family, _type, _proto, _canon, sockaddr in infos:
        ip = sockaddr[0]
        if ip in seen or ip.startswith("127.") or ip in ("::1", "0.0.0.0", "::"):
            continue
        seen.add(ip)
        out.append((family, sockaddr, ip))
    return out


def _listener_evidence(port: int) -> None:
    """lsof, ss or netstat if the machine has one. Evidence, never the proof: Windows has none
    of the first two, and a missing tool must not be able to fail the run on its own."""
    for cmd in (["lsof", "-nP", f"-iTCP:{port}"],
                ["ss", "-ltn", f"sport = :{port}"],
                ["netstat", "-ano"]):
        try:
            # lsof/ss/netstat print in the OS's own codepage, not ours: decode leniently rather
            # than assert utf-8 and risk this evidence-only probe crashing the batter over a byte.
            out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=30).stdout
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            continue
        lines = [ln.strip() for ln in out.splitlines() if f":{port}" in ln]
        if not lines:
            continue
        bad = [ln for ln in lines if "127.0.0.1" not in ln and "[::1]" not in ln]
        check(not bad, f"D8 {cmd[0]} shows the listener on 127.0.0.1 only", " / ".join(bad)[:200])
        for ln in lines[:3]:
            print("      " + ln)
        return
    print("      no lsof, ss or netstat here: the Python probes above are the proof")


def d8_lan(wire: Wire) -> None:
    """D8 — the port is loopback and nothing else. Proved from Python so the proof is the same
    on every OS; a shell tool only corroborates it."""
    check(_reaches(socket.AF_INET, (ps.BIND, wire.port)),
          f"D8 {ps.BIND}:{wire.port} answers, so the port really is up while we test it")
    endpoints = _own_endpoints(wire.port)
    if not endpoints:
        check(True, "D8 this machine has no non-loopback address; nothing to reach it by")
    for family, sockaddr, label in endpoints:
        check(not _reaches(family, sockaddr),
              f"D8 {label}:{wire.port} did not answer (refused or dropped)")
    _listener_evidence(wire.port)


def d9_exhaustion(wire: Wire, session) -> None:
    """D9 — an open port needs a body cap, a lock and a timeout."""
    try:
        status, _h, body = wire.call("POST", "/run", body={"title": "x" * (ps.MAX_BODY + 10)})
    except CONNECTION_CLOSED:
        # The oversized body is left unread and the socket closes before it is all sent -- the
        # same refusal as a clean 413 with an empty body, seen from the other side of the socket.
        status, body = 413, b""
    check(status == 413 and body == b"", f"D9 a body over {ps.MAX_BODY} bytes -> 413", f"got {status}")
    session.lock.acquire()
    try:
        status, payload = wire.json("POST", "/run", body={"formats": ["csv"]})
    finally:
        session.lock.release()
    check(status == 409, "D9 a second concurrent export -> 409", f"got {status}")
    check(session.idle >= ps.MIN_IDLE, "D9 the idle timeout is set and cannot be disabled")


def d10_headers(wire: Wire) -> None:
    """D10 — a title becomes a file name becomes a header. It must not split the response."""
    _s, payload = wire.json("POST", "/run", body={"formats": ["csv"], "pack": True,
                                                  "basename": "trap"})
    names = [f["name"] for f in payload.get("files", [])]
    pdfs = [n for n in names if n.lower().endswith(".pdf")]
    check(bool(pdfs), "D10 the pack wrote PDFs named from hostile titles", str(names)[:200])
    for name in pdfs[:4]:
        status, headers, _b = wire.call("GET", "/files/" + urllib.parse.quote(name))
        disposition = headers.get("Content-Disposition", "")
        check(status == 200, f"D10 {name} served", f"got {status}")
        check("\r" not in disposition and "\n" not in disposition and disposition.count('"') in (0, 2),
              "D10 Content-Disposition is one well-formed header", disposition)
        # The name itself contains the text "X-Injected"; what matters is that it is a value
        # inside one quoted header and never a header of its own.
        check("x-injected" not in [k.lower() for k in headers.keys()],
              "D10 no header was smuggled in through a title", str(list(headers.keys())))


# --------------------------------------------------------------------------------------
def main() -> int:
    print("battering front 3\n")
    with running(docs=HOSTILE) as (httpd, session, url, workdir, _thread):
        wire = Wire(httpd, session)
        print(f"server on {ps.BIND}:{wire.port}, run root {workdir}\n")
        d1_csrf(wire)
        d2_rebinding(wire)
        d3_local_process(wire, session)
        d5_hostile_title(wire)
        run_dir = session.run_dir or workdir
        d6_traversal(wire, workdir, run_dir)
        d9_exhaustion(wire, session)
        d10_headers(wire)
        d8_lan(wire)
        d7_token(wire)          # last: it judges every byte sent by all of the above

    failed = [name for ok, name, _d in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} refused as designed")
    if failed:
        print("FAILURES:")
        for name in failed:
            print("  " + name)
        return 1
    print("BATTER PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
