#!/usr/bin/env python3
"""Tests for front 2, the page opened from disk. Stdlib unittest; no browser and no network.

The behaviour of the engine inside the page is tested by test_front2_conformance.py, which runs it
under node against the shared fixture. This file is about the file itself: what it is, what it
carries, and what it must never carry.
"""
from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gen_rules                       # noqa: E402
import paperless_export as px          # noqa: E402
import paperless_front                 # noqa: E402

PAGE = paperless_front.PAGE
DISK = paperless_front.disk_page()
SCRIPT = PAGE.split("</style>", 1)[1]


class TestTheBuild(unittest.TestCase):
    def test_the_disk_build_is_the_served_page_plus_one_constant(self):
        self.assertIn("const DISK_BUILD = true;", DISK)
        self.assertNotIn("const DISK_BUILD = false;", DISK)
        self.assertNotIn("__CSP_NONCE__", DISK)
        # Everything else, character for character.
        self.assertEqual(DISK.replace("const DISK_BUILD = true;", "const DISK_BUILD = false;")
                             .replace("\n" + paperless_front.DISK_CSP, ""),
                         PAGE.replace(' nonce="__CSP_NONCE__"', ""))

    def test_the_constant_appears_exactly_once(self):
        """Two of them and write_disk_copy would flip one and leave the other."""
        self.assertEqual(PAGE.count("const DISK_BUILD ="), 1)

    def test_writing_the_file_writes_the_disk_build(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "front.html"
            paperless_front.write_disk_copy(str(out))
            self.assertEqual(out.read_text(encoding="utf-8"), DISK)

    def test_the_built_file_is_the_same_bytes_on_every_os(self):
        """read_text() alone would not have caught the Windows CRLF bug: universal-newline
        translation on read hides it again. The bytes on disk are what a release asset actually is.
        """
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "front.html"
            paperless_front.write_disk_copy(str(out))
            self.assertEqual(out.read_bytes(), DISK.encode("utf-8"))
            self.assertNotIn(b"\r\n", out.read_bytes())

    def test_the_served_page_is_never_the_disk_build(self):
        self.assertIn("const DISK_BUILD = false;", paperless_front.page("nonce123").decode())


class TestOneFileNoHelp(unittest.TestCase):
    def test_nothing_is_loaded_from_anywhere_else(self):
        """No script, style, image or font from another origin: the file must work with no network."""
        for banned in ("<script src", "<link ", "@import", "https://cdn", "http://cdn",
                       "unpkg", "jsdelivr", "googleapis", "<iframe"):
            self.assertNotIn(banned, PAGE, f"{banned} in the page")

    def test_the_page_carries_its_own_engine(self):
        self.assertIn("// ---- ENGINE START ----", PAGE)
        self.assertIn("// ---- ENGINE END ----", PAGE)
        self.assertIn("async function runExport(", PAGE)

    def test_the_rule_map_has_not_drifted_from_the_code(self):
        self.assertEqual(gen_rules.check(), [])

    def test_the_rule_map_in_the_page_is_the_one_in_the_engine(self):
        block = re.search(r"const RULE_MAP = (\{.*?\});", PAGE, re.S).group(1)
        for rt, (param, isnull, multi) in px.RULE_MAP.items():
            self.assertIn(f'"{rt}": [ "{param}"', block, f"rule {rt}")


class TestTheTokenStaysInTheTab(unittest.TestCase):
    def test_no_storage_of_any_kind(self):
        for banned in ("localStorage", "sessionStorage", "document.cookie", "indexedDB",
                       "requestFileSystem"):
            self.assertNotIn(banned, PAGE, f"{banned} in the page")

    def test_the_token_field_is_a_password_field_that_does_not_autofill(self):
        self.assertIn('<input type="password" id="f-token" autocomplete="off">', PAGE)

    def test_the_token_is_only_ever_a_header(self):
        """One place builds the Authorization header, and it is not a URL and not the DOM."""
        self.assertEqual(PAGE.count('"Authorization"'), 1)
        self.assertNotIn("token=", PAGE)
        self.assertNotIn("?token", PAGE)

    def test_credentials_are_never_sent(self):
        self.assertIn('credentials: "omit"', PAGE)


class TestWhatThePageRefuses(unittest.TestCase):
    def test_a_redirect_is_a_failure_not_a_follow(self):
        self.assertIn('redirect: "error"', PAGE)

    def test_it_refuses_a_url_with_a_query_or_fragment(self):
        self.assertIn("tokens never ride in URLs", PAGE)

    def test_public_http_needs_a_typed_word(self):
        self.assertIn('insecureWord !== "insecure"', PAGE)
        self.assertIn("needsInsecure", PAGE)

    def test_mixed_content_is_explained_before_it_is_attempted(self):
        self.assertIn("mixed content", PAGE)

    def test_the_private_host_rule_matches_the_command_line_where_it_can(self):
        """The browser cannot resolve a name, so the page is stricter, never looser."""
        rule = re.search(r"function isPrivateHost\(host\) \{.*?\n\}", PAGE, re.S).group(0)
        for private in ("localhost", ".local", ".home.arpa", "127", "10", "192", "168",
                        "172", "169", "254", "::1", "fe80"):
            self.assertIn(private, rule, f"{private} missing from the host rule")
        # Anything the CLI calls private by literal address, the page must call private too.
        for host in ("127.0.0.1", "10.0.0.5", "192.168.1.10", "172.16.0.1", "169.254.1.1"):
            self.assertTrue(px.is_private_host(host), host)

    def test_xlsx_and_pack_are_refused_with_a_reason(self):
        self.assertIn("xlsx and the PDF pack are command-line", PAGE)
        self.assertIn("paperless-export --pack, at the command line", PAGE)

    def test_an_unknown_config_key_is_refused_before_anything_runs(self):
        """A tags key at the top level (instead of under filters) once exported the whole archive
        with no filter and no error. The engine now refuses, in the same words the server already
        uses for the same mistake (paperless_serve.py argv_from_config)."""
        self.assertIn("unknown setting(s): ", PAGE)
        body = re.search(r"function normaliseConfig\(raw\) \{.*?\n\}", PAGE, re.S).group(0)
        self.assertIn("CONFIG_KEYS", body)
        self.assertLess(body.index("unknown"), body.index("const cfg ="),
                        "the unknown-key check must run before the config is built from raw")

    def test_collect_nests_filters_for_the_disk_engine_and_drops_pack_version(self):
        """Found live: with the unknown-key check in place, the disk build's own default form
        (nothing typed, pack_version always has a selected value) failed every run with "unknown
        setting(s): pack_version" — collect() built the server's flat shape for both fronts, but
        the disk engine's normaliseConfig takes the documented shape, filters nested. Front 3's
        server keeps taking the flat shape unchanged; only the disk mode's collect() branches.
        """
        body = re.search(r"function collect\(\) \{.*?\n\}", PAGE, re.S).group(0)
        self.assertIn('MODE === "disk" && name === "pack_version"', body)
        self.assertIn('MODE === "disk" && group === "filters" && name !== "view"', body)
        self.assertIn("config.filters = filters", body)


class TestTheCorsAdvice(unittest.TestCase):
    def test_the_named_origin_route_comes_first(self):
        help_text = re.search(r"const CORS_HELP =(.*?);\n", PAGE, re.S).group(1)
        self.assertLess(help_text.index("http.server 9001"), help_text.index("null"),
                        "the page must offer the safe route before it mentions null")

    def test_the_null_warning_says_what_it_opens(self):
        warning = re.search(r"const NULL_WARNING =(.*?);\n", PAGE, re.S).group(1)
        for word in ("sandboxed", "delete", "take it back out"):
            self.assertIn(word, warning, f"the warning does not say {word!r}")

    def test_the_readme_names_the_safe_route_before_null(self):
        readme_path = gen_rules.find_ship_doc("README.md", Path(__file__).resolve().parent)
        self.assertIsNotNone(readme_path, "README.md not found beside or above this file")
        readme = readme_path.read_text(encoding="utf-8")
        self.assertIn("PAPERLESS_CORS_ALLOWED_HOSTS", readme)
        self.assertLess(readme.index("http.server 9001"),
                        readme.index("PAPERLESS_CORS_ALLOWED_HOSTS=null"))


class TestNothingBecomesMarkup(unittest.TestCase):
    def test_no_markup_is_ever_built_from_a_value(self):
        for banned in ("innerHTML", "insertAdjacentHTML", "document.write", "outerHTML", "eval("):
            self.assertNotIn(banned, PAGE, f"{banned} in the page")

    def test_the_inventory_escapes_every_cell_it_writes(self):
        inv = re.search(r"function writeInventory\(rows, trailer\) \{.*?\n\}", PAGE, re.S).group(0)
        rendered = re.findall(r"escapeHtml\(", inv)
        self.assertGreaterEqual(len(rendered), 7)
        self.assertNotIn("${r.title}", inv)

    def test_the_disk_build_still_declares_a_policy_of_its_own(self):
        """A file has no response headers, so the CSP has to be in the document."""
        self.assertIn('http-equiv="Content-Security-Policy"', DISK)


if __name__ == "__main__":
    unittest.main()
