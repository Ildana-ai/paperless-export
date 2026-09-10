#!/usr/bin/env python3
"""front 3 — the CLI serving the page on 127.0.0.1 for one session.

Not a proxy: nothing here forwards a browser request to paperless, and the paperless token never
leaves this process.

Not adjustable, and given no flag: the bind address, the session-token check, the Host check.
"""
from __future__ import annotations

import contextlib
import hmac
import io
import json
import posixpath
import re
import secrets
import sys
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import paperless_export as px
import paperless_front

BIND = "127.0.0.1"          # literal, no flag, ever
SESSION_HEADER = "X-Session-Token"
MAX_BODY = 64 * 1024
MIN_IDLE = 60
MAX_LISTED = 250

# The config object the page may post. Anything else is a 400.
STRING_KEYS = {
    "view": "--view", "query": "--query", "title": "--title",
    "created_from": "--created-from", "created_to": "--created-to",
    "custom_field_query": "--custom-field-query", "columns": "--columns",
    "locale": "--locale", "date": "--date", "headers": "--headers",
    "list_sep": "--list-sep", "pack_version": "--pack-version",
}
LIST_KEYS = {
    "correspondent": "--correspondent", "document_type": "--document-type",
    "tags": "--tag", "storage_path": "--storage-path", "sums": "--sum",
    "formats": "--format",
}
BOOL_KEYS = {"content": "--content", "pack": "--pack", "inventory": "--inventory"}
BASENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
HEADER_SAFE = re.compile(r'^[A-Za-z0-9._ -]+$')


class BadRequest(Exception):
    """The page sent something the server will not map. Answered 400, never mapped anyway."""


# --------------------------------------------------------------------------------------
# config object -> the argv the CLI would have taken
# --------------------------------------------------------------------------------------
def argv_from_config(config: dict, out: Path, insecure: bool) -> list[str]:
    if not isinstance(config, dict):
        raise BadRequest("the config must be an object")
    unknown = set(config) - set(STRING_KEYS) - set(LIST_KEYS) - set(BOOL_KEYS) - {"basename"}
    if unknown:
        raise BadRequest(f"unknown setting(s): {', '.join(sorted(unknown))}")

    argv: list[str] = []
    for key, flag in STRING_KEYS.items():
        value = config.get(key)
        if value in (None, ""):
            continue
        if not isinstance(value, str):
            raise BadRequest(f"{key} must be text")
        # --flag=value, never two tokens: a value starting with '-' must not become a flag.
        argv.append(f"{flag}={value}")
    for key, flag in LIST_KEYS.items():
        values = config.get(key)
        if values in (None, []):
            continue
        if not isinstance(values, list) or not all(isinstance(v, str) and v for v in values):
            raise BadRequest(f"{key} must be a list of text values")
        argv.extend(f"{flag}={v}" for v in values)
    for key, flag in BOOL_KEYS.items():
        value = config.get(key, False)
        if not isinstance(value, bool):
            raise BadRequest(f"{key} must be true or false")
        if value:
            argv.append(flag)

    basename = config.get("basename") or "export"
    if not isinstance(basename, str) or not BASENAME_RE.match(basename) or ".." in basename:
        raise BadRequest("the file name must be letters, digits, dot, dash or underscore, 64 max")
    argv.append(f"--output={out / basename}")
    if insecure:
        argv.append("--insecure")     # inherited from launch; the page cannot set it
    return argv


def defaults_from_args(args) -> dict:
    """The launch flags, as the page's starting values. A default is a convenience, not a right."""
    return {
        "view": args.view, "query": args.query, "title": args.title,
        "correspondent": args.correspondent, "document_type": args.document_type,
        "tags": args.tags, "storage_path": args.storage_path,
        "created_from": args.created_from, "created_to": args.created_to,
        "custom_field_query": args.custom_field_query,
        "sums": args.sums, "columns": args.columns, "content": args.content,
        "locale": args.locale, "date": args.date, "headers": args.headers or "",
        "list_sep": args.list_sep, "formats": args.formats or ["csv"],
        "pack": args.pack, "pack_version": args.pack_version, "inventory": args.inventory,
        "basename": Path(args.output).name or "export",
    }


# --------------------------------------------------------------------------------------
# session
# --------------------------------------------------------------------------------------
class Session:
    """One per process. There is no re-arm: when it ends, the process ends."""

    def __init__(self, defaults: dict, instance: str, idle: int, insecure: bool):
        self.token = secrets.token_urlsafe(32)
        self.url_form_spent = False
        self.defaults = defaults
        self.instance = instance
        self.idle = idle
        self.insecure = insecure
        self.lock = threading.Lock()          # one export at a time
        self.manifest: dict[str, Path] = {}   # name as served -> resolved path
        self.run_dir: Path | None = None
        self.last_seen = time.time()

    def check(self, presented: str | None) -> bool:
        return bool(presented) and hmac.compare_digest(presented, self.token)

    def spend_url_form(self, presented: str) -> bool:
        """The ?s= form is good once. A second use is worth nothing to whoever copied it."""
        if self.url_form_spent or not self.check(presented):
            return False
        self.url_form_spent = True
        return True

    def next_run_dir(self) -> Path:
        """Where a run would write. Nothing is created and nothing is forgotten yet."""
        return (Path.cwd() / f"paperless-export-{time.strftime('%Y%m%d-%H%M%S')}").resolve()

    def begin_run(self, run: Path) -> Path:
        """The old run's links die here, not before: a settings error must leave them serving."""
        run.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.run_dir = run
        self.manifest = {}
        return self.run_dir

    def remember(self, paths: list[Path]) -> list[dict]:
        listed = []
        for path in paths:
            resolved = Path(path).resolve()
            try:
                name = resolved.relative_to(self.run_dir).as_posix()
            except ValueError:
                continue          # not ours to serve
            self.manifest[name] = resolved
            listed.append({"name": name, "bytes": resolved.stat().st_size})
        return listed


# --------------------------------------------------------------------------------------
# handler
# --------------------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "paperless-export"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    @property
    def session(self) -> Session:
        return self.server.session

    @property
    def expect_host(self) -> str:
        return self.server.expect_host

    # -- plumbing ----------------------------------------------------------------------
    def log_message(self, fmt, *args):      # noqa: A003 - http.server's own name
        """One line per request: method, path, status. No query string — the token was in it."""
        return

    def _log(self, status: int) -> None:
        path = self.path.split("?", 1)[0]
        sys.stderr.write(f"{self.command} {path} {status}\n")
        sys.stderr.flush()

    def _send(self, status: int, body: bytes = b"", ctype: str | None = None,
              nonce: str | None = None, extra: dict | None = None) -> None:
        self.send_response(status)
        if ctype:
            self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        csp = ("default-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        if nonce:
            csp += f"; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; connect-src 'self'"
        self.send_header("Content-Security-Policy", csp)
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
        self._log(status)

    def _json(self, status: int, payload: dict) -> None:
        self._send(status, json.dumps(payload).encode("utf-8"), "application/json")

    def _authed(self) -> bool:
        """Header and Host, both — CSRF and DNS rebinding, refused by one pair of checks."""
        if (self.headers.get("Host") or "") != self.expect_host:
            return False
        return self.session.check(self.headers.get(SESSION_HEADER))

    def _deny(self) -> None:
        # Empty body: an error message is a free oracle telling the attacker which check they failed.
        # The connection closes because a denied POST leaves its body unread on the socket.
        self.close_connection = True
        self._send(403)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            self.close_connection = True     # the body stays on the socket; don't reuse it
            self._send(413)
            return None
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise BadRequest("that was not JSON")

    # -- routes ------------------------------------------------------------------------
    def do_OPTIONS(self):    # noqa: N802
        """No CORS answer, ever. A preflight that never succeeds is a POST that never arrives."""
        self._deny()

    def do_GET(self):        # noqa: N802
        self.session.last_seen = time.time()
        path, _, query = self.path.partition("?")
        if path == "/":
            return self._page(query)
        if not self._authed():
            return self._deny()
        if path == "/session":
            return self._json(200, {
                "version": px.__version__,
                "instance": self.session.instance,
                "defaults": self.session.defaults,
                "xlsx": _have_openpyxl(),
                "idle": self.session.idle,
            })
        if path.startswith("/files/"):
            return self._file(path[len("/files/"):])
        self._send(404)

    def do_POST(self):       # noqa: N802
        self.session.last_seen = time.time()
        path = self.path.split("?", 1)[0]
        if not self._authed():
            return self._deny()
        try:
            payload = self._body()
        except BadRequest as exc:
            return self._json(400, {"ok": False, "error": str(exc)})
        if payload is None:
            return                      # 413 already sent
        if path == "/quit":
            self._json(200, {"ok": True})
            return _shutdown(self.server)
        if path == "/run":
            return self._run(payload)
        self._send(404)

    def do_HEAD(self):       # noqa: N802
        self._send(404)

    # -- the three things it serves ----------------------------------------------------
    def _page(self, query: str) -> None:
        presented = urllib.parse.parse_qs(query).get("s", [""])[0]
        if presented and not self.session.spend_url_form(presented):
            return self._deny()         # wrong, or already spent
        nonce = secrets.token_urlsafe(16)
        self._send(200, paperless_front.page(nonce), "text/html; charset=utf-8", nonce=nonce)

    def _file(self, raw_name: str) -> None:
        name = urllib.parse.unquote(raw_name)
        if not name or "\x00" in name or name.startswith("/") or name.startswith(".."):
            return self._send(404)
        name = posixpath.normpath(name)
        if name.startswith("..") or name.startswith("/"):
            return self._send(404)
        target = self.session.manifest.get(name)      # we serve what the run wrote, not what we find
        if target is None or self.session.run_dir is None:
            return self._send(404)
        try:
            resolved = target.resolve(strict=True)
            resolved.relative_to(self.session.run_dir)     # and it must still be inside the run
        except (OSError, ValueError):
            return self._send(404)
        body = resolved.read_bytes()
        extra = {}
        leaf = resolved.name
        if HEADER_SAFE.match(leaf):
            extra["Content-Disposition"] = f'attachment; filename="{leaf}"'
        else:
            extra["Content-Disposition"] = "attachment"
        # Octet-stream on purpose: the run's own inventory is HTML and must not render in our origin.
        self._send(200, body, "application/octet-stream", extra=extra)

    def _run(self, config: dict) -> None:
        if not self.session.lock.acquire(blocking=False):
            return self._json(409, {"ok": False, "error": "an export is already running"})
        try:
            run_dir = self.session.next_run_dir()
            argv = argv_from_config(config, run_dir, self.session.insecure)
            cfg = _config_or_400(argv)
            self.session.begin_run(run_dir)     # validated: now the directory and the manifest move
            result = px.export(cfg)
            files = self.session.remember(list(result["files"]) + list(result["packed"]))
            trailer = {str(k): str(v) for k, v in result["trailer"].items()}
            payload = {"ok": True, "trailer": trailer, "files": files[:MAX_LISTED],
                       "run_dir": str(run_dir)}
            if len(files) > MAX_LISTED:
                payload["more"] = len(files) - MAX_LISTED
            self._json(200, payload)
        except BadRequest as exc:
            self._json(400, {"ok": False, "error": px.redact(str(exc)), "exit": px.EXIT_USAGE})
        except px.UsageError as exc:
            self._json(400, {"ok": False, "error": px.redact(f"usage error: {exc}"), "exit": px.EXIT_USAGE})
        except px.ReconcileError as exc:
            self._json(500, {"ok": False, "error": px.redact(f"RECONCILIATION FAILED: {exc}"),
                             "exit": px.EXIT_RECONCILE})
        except px.ExportError as exc:
            self._json(500, {"ok": False, "error": px.redact(f"export failed: {exc}"), "exit": px.EXIT_FAIL})
        except Exception as exc:                      # never leak a traceback to the browser
            self._json(500, {"ok": False, "error": px.redact(f"export failed: {exc.__class__.__name__}"),
                             "exit": px.EXIT_FAIL})
        finally:
            self.session.lock.release()


def _config_or_400(argv: list[str]):
    """One validator for every front. argparse exits the process on a bad value; not here it doesn't."""
    err = io.StringIO()
    try:
        with contextlib.redirect_stderr(err):
            return px.config_from_args(argv)
    except SystemExit:
        message = err.getvalue().strip().splitlines()
        raise BadRequest(message[-1] if message else "that setting is not allowed") from None


def _have_openpyxl() -> bool:
    try:
        import openpyxl  # noqa: F401
        return True
    except ImportError:
        return False


def _shutdown(server) -> None:
    threading.Thread(target=server.shutdown, daemon=True).start()


# --------------------------------------------------------------------------------------
# serve
# --------------------------------------------------------------------------------------
def build_server(argv: list[str]) -> tuple[ThreadingHTTPServer, Session, str]:
    args = px.build_parser().parse_args(argv)
    if args.idle < MIN_IDLE:
        raise px.UsageError(f"--idle must be at least {MIN_IDLE} seconds; it cannot be disabled")
    # Fails here, exit 2, before a port is opened or a browser launched.
    cfg = px.config_from_args(argv)

    session = Session(defaults_from_args(args), cfg.base_url, args.idle, cfg.insecure)
    httpd = ThreadingHTTPServer((BIND, 0), Handler)
    httpd.daemon_threads = True
    port = httpd.server_address[1]
    httpd.session = session
    httpd.expect_host = f"{BIND}:{port}"
    return httpd, session, f"http://{BIND}:{port}/?s={session.token}"


def _idle_watch(httpd, session: Session) -> None:
    while True:
        time.sleep(5)
        if time.time() - session.last_seen > session.idle:
            sys.stderr.write(f"idle {session.idle}s, shutting down\n")
            _shutdown(httpd)
            return


def serve(argv: list[str]) -> int:
    try:
        httpd, session, url = build_server(argv)
    except px.UsageError as exc:
        print(px.redact(f"usage error: {exc}"), file=sys.stderr)
        return px.EXIT_USAGE
    args = px.build_parser().parse_args(argv)

    # flush: the URL is the whole point of the command, and a piped stdout would hold it back.
    print(f"paperless-export {px.__version__} - one session, {BIND} only, no CORS change needed")
    print(f"  {url}")
    print(f"  files land in {Path.cwd() / 'paperless-export-<date-time>'}")
    print(f"  the link works once; it dies on Ctrl-C, on Quit, or after {args.idle}s idle",
          flush=True)
    if not args.no_open:
        webbrowser.open(url)

    threading.Thread(target=_idle_watch, args=(httpd, session), daemon=True).start()
    try:
        httpd.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
    finally:
        httpd.server_close()
    return px.EXIT_OK
