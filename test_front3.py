#!/usr/bin/env python3
"""Tests for front 3, the loopback front. Stdlib unittest; no live paperless needed.

Run: python3 -m unittest discover -s execution -v
The other half of verification is execution/test_front3_batter.py, which attacks a real server.
"""
from __future__ import annotations

import contextlib
import http.client
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import paperless_export as px          # noqa: E402
import paperless_front                 # noqa: E402
import paperless_serve as ps           # noqa: E402
from test_paperless_export import DOCS, FakeClient   # noqa: E402

ARGV = ["--serve"]


@contextlib.contextmanager
def running(argv=None, docs=None):
    """A real server on a real port, with the fixture standing in for paperless."""
    os.environ["PAPERLESS_URL"] = "https://paperless.test"
    os.environ["PAPERLESS_TOKEN"] = "fixture-token-do-not-leak"
    original = px.Client
    px.Client = lambda *a, **k: FakeClient(docs=docs)
    workdir = tempfile.mkdtemp()
    here = os.getcwd()
    os.chdir(workdir)
    httpd, session, url = ps.build_server(argv or ARGV)
    thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        yield httpd, session, url, Path(workdir), thread
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        px.Client = original
        os.chdir(here)
        # The runs write into workdir, so the sweep goes here and it goes on the failure path too:
        # a batter run on the Linux client left a run directory in /tmp behind.
        shutil.rmtree(workdir, ignore_errors=True)


class Wire:
    """A tiny client that keeps every byte the server sent, so a test can search it."""

    def __init__(self, httpd, session):
        self.host, self.port = httpd.server_address[0], httpd.server_address[1]
        self.session = session
        self.seen: list[bytes] = []

    def call(self, method, path, token="auto", host="auto", body=None, headers=None):
        conn = http.client.HTTPConnection(self.host, self.port, timeout=10)
        sent = dict(headers or {})
        if token == "auto":
            sent[ps.SESSION_HEADER] = self.session.token
        elif token is not None:
            sent[ps.SESSION_HEADER] = token
        if host == "auto":
            sent["Host"] = f"{ps.BIND}:{self.port}"
        elif host is not None:
            sent["Host"] = host
        payload = json.dumps(body).encode() if body is not None else None
        if payload is not None:
            sent["Content-Type"] = "application/json"
        try:
            conn.request(method, path, body=payload, headers=sent)
            response = conn.getresponse()
            raw = response.read()
            self.seen.append(raw)
            self.seen.append(str(response.headers).encode())
            return response.status, response.headers, raw
        finally:
            conn.close()

    def json(self, *args, **kw):
        status, headers, raw = self.call(*args, **kw)
        return status, json.loads(raw.decode())


# --------------------------------------------------------------------------------------
class TestThePage(unittest.TestCase):
    def test_served_bytes_are_the_page_with_only_the_nonce_filled(self):
        served = paperless_front.page("nonce123")
        self.assertEqual(served.decode(), paperless_front.PAGE.replace("__CSP_NONCE__", "nonce123"))
        self.assertNotIn(b"__CSP_NONCE__", served)

    def test_disk_copy_is_the_same_page(self):
        """One page. The disk build differs by the nonce attribute and the build constant, and by
        nothing else."""
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "front.html"
            paperless_front.write_disk_copy(str(out))
            written = out.read_text(encoding="utf-8")
        self.assertNotIn("__CSP_NONCE__", written)
        self.assertEqual(written, paperless_front.disk_page())
        self.assertEqual(written.replace("\n" + paperless_front.DISK_CSP, "")
                         .replace("const DISK_BUILD = true;", "const DISK_BUILD = false;"),
                         paperless_front.PAGE.replace(' nonce="__CSP_NONCE__"', ""))
        self.assertIn("const DISK_BUILD = false;", paperless_front.page("abc").decode())

    def test_page_never_builds_markup_from_a_value(self):
        for banned in ("innerHTML", "insertAdjacentHTML", "document.write", "outerHTML", "eval("):
            self.assertNotIn(banned, paperless_front.PAGE, f"{banned} in the page")

    def test_page_keeps_the_token_nowhere_that_outlives_the_tab(self):
        for banned in ("localStorage", "sessionStorage", "document.cookie"):
            self.assertNotIn(banned, paperless_front.PAGE)
        self.assertIn("history.replaceState", paperless_front.PAGE)

    def test_served_mode_is_decided_by_the_protocol_and_the_token_only(self):
        self.assertIn('location.protocol === "http:" && token', paperless_front.PAGE)

    def test_no_inline_style_attribute_survives_the_csp(self):
        """A nonce covers a <style> block, never a style="" attribute; default-src none blocks it."""
        body = paperless_front.PAGE.split("</style>", 1)[1]
        self.assertNotIn('style="', body)

    def test_nonce_must_be_url_safe(self):
        with self.assertRaises(ValueError):
            paperless_front.page('"><script>')


class TestConfigMapping(unittest.TestCase):
    def map(self, config, insecure=False):
        return ps.argv_from_config(config, Path("/tmp/run"), insecure)

    def test_a_full_config_maps_to_the_argv_the_cli_would_take(self):
        argv = self.map({"view": "Tax", "tags": ["a", "b"], "formats": ["csv", "json"],
                         "pack": True, "basename": "sheet", "locale": "comma"})
        self.assertIn("--view=Tax", argv)
        self.assertIn("--tag=a", argv)
        self.assertIn("--tag=b", argv)
        self.assertIn("--format=csv", argv)
        self.assertIn("--pack", argv)
        self.assertIn("--locale=comma", argv)
        self.assertIn(f"--output={Path('/tmp/run') / 'sheet'}", argv)

    def test_a_value_starting_with_a_dash_stays_a_value(self):
        """--flag=value, never two tokens, so a title can never become a flag."""
        argv = self.map({"title": "--insecure"})
        self.assertIn("--title=--insecure", argv)
        self.assertNotIn("--insecure", argv)

    def test_unknown_key_refused(self):
        with self.assertRaises(ps.BadRequest):
            self.map({"token": "hunter2"})
        with self.assertRaises(ps.BadRequest):
            self.map({"insecure": True})
        with self.assertRaises(ps.BadRequest):
            self.map({"output": "/etc/passwd"})

    def test_wrong_types_refused(self):
        for config in ({"view": ["a"]}, {"tags": "a"}, {"tags": [1]}, {"pack": "yes"}, {"tags": [""]}):
            with self.assertRaises(ps.BadRequest):
                self.map(config)

    def test_basename_is_a_name_and_nothing_else(self):
        for bad in ("../out", "a/b", ".hidden", "x" * 65, "", " ", "a\x00b"):
            with self.assertRaises(ps.BadRequest):
                self.map({"basename": bad} if bad else {"basename": bad or "."})

    def test_insecure_is_inherited_from_launch_and_never_from_the_page(self):
        self.assertIn("--insecure", self.map({}, insecure=True))
        self.assertNotIn("--insecure", self.map({}, insecure=False))

    def test_defaults_carry_the_launch_flags(self):
        args = px.build_parser().parse_args(["--serve", "--tag=tax", "--format=json", "-o", "books"])
        defaults = ps.defaults_from_args(args)
        self.assertEqual(defaults["tags"], ["tax"])
        self.assertEqual(defaults["formats"], ["json"])
        self.assertEqual(defaults["basename"], "books")


class TestAuthMatrix(unittest.TestCase):
    def test_the_page_needs_nothing_and_everything_else_needs_both(self):
        with running() as (httpd, session, url, _wd, thread):
            wire = Wire(httpd, session)
            status, _h, body = wire.call("GET", "/", token=None)
            self.assertEqual(status, 200)
            self.assertIn(b"paperless-export", body)

            self.assertEqual(wire.call("GET", "/session", token=None)[0], 403)
            self.assertEqual(wire.call("GET", "/session", token="wrong")[0], 403)
            self.assertEqual(wire.call("GET", "/session", host="evil.example")[0], 403)
            self.assertEqual(wire.call("GET", "/session", host=f"localhost:{wire.port}")[0], 403)
            self.assertEqual(wire.call("OPTIONS", "/run")[0], 403)
            self.assertEqual(wire.call("GET", "/nope")[0], 404)
            status, payload = wire.json("GET", "/session")
            self.assertEqual(status, 200)
            self.assertEqual(payload["instance"], "https://paperless.test")

    def test_a_denial_says_nothing(self):
        with running() as (httpd, session, url, _wd, thread):
            wire = Wire(httpd, session)
            _s, _h, body = wire.call("GET", "/session", token="wrong")
            self.assertEqual(body, b"")

    def test_the_url_form_of_the_token_works_once(self):
        with running() as (httpd, session, url, _wd, thread):
            wire = Wire(httpd, session)
            query = "/?s=" + session.token
            self.assertEqual(wire.call("GET", query, token=None)[0], 200)
            self.assertEqual(wire.call("GET", query, token=None)[0], 403)
            self.assertEqual(wire.call("GET", "/", token=None)[0], 200)

    def test_a_wrong_url_token_is_refused_and_does_not_spend_the_good_one(self):
        with running() as (httpd, session, url, _wd, thread):
            wire = Wire(httpd, session)
            self.assertEqual(wire.call("GET", "/?s=nope", token=None)[0], 403)
            self.assertEqual(wire.call("GET", "/?s=" + session.token, token=None)[0], 200)

    def test_the_response_headers_are_on_everything(self):
        with running() as (httpd, session, url, _wd, thread):
            wire = Wire(httpd, session)
            for path in ("/", "/session"):
                _s, headers, _b = wire.call("GET", path)
                self.assertEqual(headers["Cache-Control"], "no-store")
                self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
                self.assertEqual(headers["Referrer-Policy"], "no-referrer")
                self.assertIn("default-src 'none'", headers["Content-Security-Policy"])
            _s, headers, body = wire.call("GET", "/")
            csp = headers["Content-Security-Policy"]
            self.assertIn("connect-src 'self'", csp)
            nonce = csp.split("'nonce-")[1].split("'")[0]
            self.assertIn(f'nonce="{nonce}"'.encode(), body)

    def test_the_nonce_is_fresh_per_response(self):
        with running() as (httpd, session, url, _wd, thread):
            wire = Wire(httpd, session)
            first = wire.call("GET", "/")[1]["Content-Security-Policy"]
            second = wire.call("GET", "/")[1]["Content-Security-Policy"]
            self.assertNotEqual(first, second)


class TestRunning(unittest.TestCase):
    def test_a_run_writes_the_files_and_answers_with_the_trailer(self):
        with running() as (httpd, session, url, workdir, thread):
            wire = Wire(httpd, session)
            status, payload = wire.json("POST", "/run", body={"formats": ["csv", "json"],
                                                              "basename": "sheet"})
            self.assertEqual(status, 200, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["trailer"]["rows written"], str(len(DOCS)))
            self.assertEqual(payload["trailer"]["api count"], str(len(DOCS)))
            names = sorted(f["name"] for f in payload["files"])
            self.assertEqual(names, ["sheet.csv", "sheet.json"])
            run_dir = Path(payload["run_dir"])
            self.assertTrue((run_dir / "sheet.csv").exists())
            self.assertEqual(run_dir.parent.resolve(), workdir.resolve())

    @unittest.skipIf(sys.platform == "win32",
                      "0700 is not a POSIX-mode control on Windows: the run directory inherits the "
                      "user's profile ACL and nothing more is claimed there")
    def test_the_run_directory_is_not_world_readable(self):
        with running() as (httpd, session, url, _wd, thread):
            wire = Wire(httpd, session)
            _s, payload = wire.json("POST", "/run", body={"formats": ["csv"]})
            mode = Path(payload["run_dir"]).stat().st_mode & 0o777
            self.assertEqual(mode, 0o700)

    def test_files_are_served_by_name_as_attachments_and_nothing_else_is(self):
        with running() as (httpd, session, url, _wd, thread):
            wire = Wire(httpd, session)
            wire.json("POST", "/run", body={"formats": ["csv"], "basename": "sheet"})
            status, headers, body = wire.call("GET", "/files/sheet.csv")
            self.assertEqual(status, 200)
            self.assertEqual(headers["Content-Type"], "application/octet-stream")
            self.assertIn("attachment", headers["Content-Disposition"])
            self.assertTrue(body.startswith(b"\xef\xbb\xbf"))
            for miss in ("/files/", "/files/other.csv", "/files/sheet.json"):
                self.assertEqual(wire.call("GET", miss)[0], 404)

    def test_a_bad_setting_is_a_400_with_the_cli_exit_code(self):
        with running() as (httpd, session, url, _wd, thread):
            wire = Wire(httpd, session)
            status, payload = wire.json("POST", "/run", body={"locale": "klingon"})
            self.assertEqual(status, 400)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["exit"], px.EXIT_USAGE)
            status, payload = wire.json("POST", "/run", body={"token": "x"})
            self.assertEqual(status, 400)
            self.assertIn("unknown setting", payload["error"])

    def test_a_failed_run_leaves_the_last_good_run_serving(self):
        with running() as (httpd, session, url, _wd, thread):
            wire = Wire(httpd, session)
            _s, good = wire.json("POST", "/run", body={"formats": ["csv", "json"],
                                                       "basename": "sheet"})
            names = [f["name"] for f in good["files"]]
            self.assertEqual(wire.json("POST", "/run", body={"locale": "klingon"})[0], 400)
            for name in names:
                self.assertEqual(wire.call("GET", "/files/" + name)[0], 200, name)
            self.assertEqual(session.run_dir, Path(good["run_dir"]))

    def test_a_failed_run_creates_no_directory(self):
        with running() as (httpd, session, url, workdir, thread):
            wire = Wire(httpd, session)
            before = sorted(p.name for p in workdir.iterdir())
            for bad in ({"locale": "klingon"}, {"token": "x"}, {"basename": "../escape"},
                        {"date": "%Q"}, {"formats": "csv"}):
                self.assertEqual(wire.json("POST", "/run", body=bad)[0], 400, bad)
            self.assertEqual(sorted(p.name for p in workdir.iterdir()), before)
            self.assertIsNone(session.run_dir)

    def test_the_lock_releases_before_the_response_is_sent(self):
        """A client that has read a reply for request N must never be able to race request N+1
        against N's own lock — found as a real flake: a run of sequential bad /run bodies, each
        meant to return 400, got a 409 because an earlier request's lock outlived its own response.
        """
        events: list[str] = []

        class WatchedLock:
            def __init__(self, inner):
                self._inner = inner

            def acquire(self, *args, **kwargs):
                return self._inner.acquire(*args, **kwargs)

            def release(self):
                events.append("release")
                return self._inner.release()

        with running() as (httpd, session, url, _wd, thread):
            session.lock = WatchedLock(session.lock)
            original_json = ps.Handler._json

            def watched_json(self, status, payload):
                events.append("json")
                return original_json(self, status, payload)

            ps.Handler._json = watched_json
            try:
                wire = Wire(httpd, session)
                status, _payload = wire.json("POST", "/run", body={"locale": "klingon"})
            finally:
                ps.Handler._json = original_json
            self.assertEqual(status, 400)
            self.assertEqual(events, ["release", "json"])

    def test_a_reconciliation_failure_reaches_the_browser_as_loudly_as_the_terminal(self):
        os.environ["PAPERLESS_URL"] = "https://paperless.test"
        os.environ["PAPERLESS_TOKEN"] = "fixture-token-do-not-leak"
        original = px.Client
        px.Client = lambda *a, **k: FakeClient(count=99)
        try:
            with running() as (httpd, session, url, _wd, thread):
                px.Client = lambda *a, **k: FakeClient(count=99)
                wire = Wire(httpd, session)
                status, payload = wire.json("POST", "/run", body={"formats": ["csv"]})
                self.assertEqual(status, 500)
                self.assertEqual(payload["exit"], px.EXIT_RECONCILE)
                self.assertIn("RECONCILIATION FAILED", payload["error"])
        finally:
            px.Client = original

    def test_one_export_at_a_time(self):
        with running() as (httpd, session, url, _wd, thread):
            wire = Wire(httpd, session)
            session.lock.acquire()
            try:
                status, payload = wire.json("POST", "/run", body={"formats": ["csv"]})
            finally:
                session.lock.release()
            self.assertEqual(status, 409)

    def test_an_oversized_body_is_refused_before_it_is_read(self):
        with running() as (httpd, session, url, _wd, thread):
            wire = Wire(httpd, session)
            status, _h, body = wire.call("POST", "/run", body={"title": "x" * (ps.MAX_BODY + 10)})
            self.assertEqual(status, 413)
            self.assertEqual(body, b"")

    def test_quit_ends_the_session(self):
        with running() as (httpd, session, url, _wd, thread):
            wire = Wire(httpd, session)
            status, payload = wire.json("POST", "/quit", body={})
            self.assertEqual(status, 200)
            self.assertTrue(payload["ok"])
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive(), "Quit did not stop the server")


class TestTheTokenNeverTravels(unittest.TestCase):
    def test_no_byte_the_server_sent_carries_the_paperless_token(self):
        with running() as (httpd, session, url, _wd, thread):
            wire = Wire(httpd, session)
            wire.call("GET", "/")
            wire.call("GET", "/session")
            wire.json("POST", "/run", body={"formats": ["csv", "json"], "inventory": True})
            wire.call("GET", "/files/export.csv")
            wire.call("GET", "/session", token="wrong")
            secret = os.environ["PAPERLESS_TOKEN"].encode()
            for chunk in wire.seen:
                self.assertNotIn(secret, chunk)

    def test_the_session_token_is_compared_in_constant_time(self):
        source = Path(ps.__file__).read_text(encoding="utf-8")
        self.assertIn("hmac.compare_digest", source)
        self.assertNotIn("presented == self.token", source)

    def test_the_log_line_carries_no_query_string(self):
        with running() as (httpd, session, url, _wd, thread):
            wire = Wire(httpd, session)
            captured = io.StringIO()
            stderr = sys.stderr
            sys.stderr = captured
            try:
                wire.call("GET", "/?s=" + session.token, token=None)
                time.sleep(0.2)
            finally:
                sys.stderr = stderr
            self.assertIn("GET / 200", captured.getvalue())
            self.assertNotIn(session.token, captured.getvalue())


class TestTheHarnessCleansUp(unittest.TestCase):
    def test_running_leaves_nothing_in_the_temp_root(self):
        original = tempfile.tempdir
        with tempfile.TemporaryDirectory() as root:
            tempfile.tempdir = root
            try:
                before = sorted(os.listdir(root))
                with running() as (httpd, session, url, _wd, thread):
                    wire = Wire(httpd, session)
                    self.assertEqual(wire.json("POST", "/run", body={"formats": ["csv"]})[0], 200)
                self.assertEqual(sorted(os.listdir(root)), before)
                with self.assertRaises(ZeroDivisionError):
                    with running() as (httpd, session, url, _wd, thread):
                        Wire(httpd, session).json("POST", "/run", body={"formats": ["csv"]})
                        1 / 0                     # the failure path must sweep too
                self.assertEqual(sorted(os.listdir(root)), before)
            finally:
                tempfile.tempdir = original


class TestTheSessionDies(unittest.TestCase):
    def test_idle_shuts_the_server_down(self):
        """The timer against a stand-in server, so the assertion is what it called, not a race."""
        class Stub:
            def __init__(self):
                self.fired = threading.Event()

            def shutdown(self):
                self.fired.set()

        stub = Stub()
        session = ps.Session({}, "https://paperless.test", 0.1, False)
        session.last_seen = time.time() - 30
        with contextlib.redirect_stderr(io.StringIO()):
            threading.Thread(target=ps._idle_watch, args=(stub, session), daemon=True).start()
            self.assertTrue(stub.fired.wait(timeout=15), "the idle watch never fired")

    def test_a_request_keeps_the_session_alive(self):
        with running() as (httpd, session, url, _wd, thread):
            session.last_seen = 0
            Wire(httpd, session).call("GET", "/session")
            self.assertGreater(session.last_seen, time.time() - 5)

    def test_idle_cannot_be_disabled(self):
        os.environ["PAPERLESS_URL"] = "https://paperless.test"
        os.environ["PAPERLESS_TOKEN"] = "t"
        for bad in ("0", "1", "-5"):
            with self.assertRaises(px.UsageError):
                ps.build_server(["--serve", "--idle", bad])

    def test_quit_ends_the_process_even_with_a_connection_still_open(self):
        """A browser keeps its connection open. Quit must still return the terminal, not hang it."""
        env = dict(os.environ, PAPERLESS_URL="https://paperless.test",
                   PAPERLESS_TOKEN="fixture-token-do-not-leak",
                   PYTHONPATH=str(Path(__file__).resolve().parent))
        workdir = tempfile.mkdtemp()
        try:
            proc = subprocess.Popen(
                [sys.executable, "-c",
                 "import paperless_serve, sys; sys.exit(paperless_serve.serve("
                 "['--serve', '--no-open']))"],
                cwd=workdir, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace")
            url = ""
            for _ in range(5):
                line = proc.stdout.readline()
                if "?s=" in line:
                    url = line.strip()
                    break
            self.assertIn("?s=", url, "the server never printed its URL")
            port = int(url.split("://127.0.0.1:")[1].split("/")[0])
            token = url.split("?s=")[1]

            # A parked keep-alive connection, exactly like a browser's.
            parked = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            parked.request("GET", "/", headers={"Host": f"127.0.0.1:{port}",
                                                ps.SESSION_HEADER: token})
            parked.getresponse().read()

            quitter = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            quitter.request("POST", "/quit", body=b"{}",
                            headers={"Host": f"127.0.0.1:{port}", ps.SESSION_HEADER: token,
                                     "Content-Type": "application/json"})
            quitter.getresponse().read()
            quitter.close()
            try:
                self.assertEqual(proc.wait(timeout=15), 0)
            except subprocess.TimeoutExpired:
                proc.kill()
                self.fail("Quit closed the port and left the command running")
            finally:
                parked.close()
                proc.stdout.close()
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    def test_there_is_no_way_to_expose_the_port(self):
        flags = str(px.build_parser().format_help())
        for banned in ("--host", "--bind", "--port", "--lan", "--expose"):
            self.assertNotIn(banned, flags)
        self.assertEqual(ps.BIND, "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
