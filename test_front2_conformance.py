#!/usr/bin/env python3
"""Both engines, one fixture, the same bytes.

The page carries a second implementation of the export in JavaScript. Two implementations drift;
this is the test that fails when they do. It runs the Python engine and the page's engine over
`fixture_v10.json` and compares what they wrote, byte for byte, at every switch's default and at
one non-default value.

`node` is required and the test skips without it, the way the xlsx tests skip without openpyxl.
A skip is not a pass: the release checklist says this test must have actually run.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import paperless_export as px          # noqa: E402
import paperless_front                 # noqa: E402
from test_paperless_export import FIXTURE, FakeClient, make_cfg   # noqa: E402

# The second document set in the same fixture: a formula title, a quote, a CR, the CSV separator
# inside a cell, a tab, non-ASCII, an ASN of 0, a tag id with no tag, a select option with no
# label, a monetary value that totals to a whole number (Python prints 10.0 where JavaScript
# prints 10), a negative integer, and a negative decimal monetary (the comma-locale guard-order
# case: a rendered "-12,50" must never pick up the formula prefix). Both engines are fed it from
# this one file.
HOSTILE = FIXTURE["hostile_documents"]

HERE = Path(__file__).resolve().parent
NODE = shutil.which("node")
ENGINE_RE = re.compile(r"// ---- ENGINE START ----.*?// ---- ENGINE END ----", re.S)

# The two values a clock decides. Everything else in the trailer must match exactly.
STAMP = "2026-01-02T03:04:05"
ELAPSED = "0.0s"

CASES = {
    "default": {},
    "locale_comma": {"locale": "comma"},
    "date_us": {"date": "us"},
    "date_eu": {"date": "eu"},
    "headers_raw": {"headers": "raw"},
    "headers_readable": {"headers": "readable"},
    "list_sep": {"list_sep": " | "},
    "columns": {"columns": "url,title,id"},
    "content": {"content": True},
    "sums": {"sums": ["Amount"]},
    "view": {"view": "Tax Invoices 2025"},
    "inventory": {"inventory": True},
    "everything": {"locale": "comma", "date": "eu", "headers": "raw", "list_sep": " / ",
                   "sums": ["Amount", "Invoice Number"], "inventory": True, "content": True},
}
FORMATS = ["csv", "json", "jsonl"]


def engine_source() -> str:
    match = ENGINE_RE.search(paperless_front.PAGE)
    if not match:
        raise AssertionError("the page has no engine block between its markers")
    return match.group(0)


def normalise(text: str) -> str:
    """The clock is not the engine. Everything else is."""
    text = re.sub(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d", STAMP, text)
    return re.sub(r"\b\d+\.\d+s\b", ELAPSED, text)


def python_run(case: dict, docs=None) -> dict[str, str]:
    kw = dict(case)
    cfg_kw = {}
    if kw.pop("locale", None) == "comma":
        cfg_kw.update(separator=";", decimal=",")
    if "date" in kw:
        spec = kw.pop("date")
        cfg_kw.update(date_spec=spec, date_fmt=px.resolve_date_format(spec))
    for key in ("headers", "list_sep", "content", "sums", "view", "inventory"):
        if key in kw:
            cfg_kw[key] = kw.pop(key)
    if "columns" in kw:
        cfg_kw["columns"] = kw.pop("columns").split(",")
    assert not kw, f"unmapped case keys {sorted(kw)}"

    out: dict[str, str] = {}
    with tempfile.TemporaryDirectory() as td:
        cfg = make_cfg(base_url=FIXTURE["base_url"], output=Path(td) / "export",
                       formats=list(FORMATS), **cfg_kw)
        original = px.Client
        px.Client = lambda *a, **k: FakeClient(docs=docs)
        try:
            result = px.export(cfg)
        finally:
            px.Client = original
        for path in result["files"]:
            # Bytes, decoded without stripping: the BOM and the CRLFs are part of what must match.
            out[path.name] = normalise(path.read_bytes().decode("utf-8"))
        out["_trailer"] = json.dumps({k: str(v) for k, v in result["trailer"].items()
                                      if k not in ("generated", "elapsed")}, sort_keys=True)
    return out


DRIVER = r"""
const fs = require("fs");
const ENGINE = require(process.argv[2]);
const fixture = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const cases = JSON.parse(fs.readFileSync(process.argv[4], "utf8"));
const docs = process.argv[5] === "hostile" ? fixture.hostile_documents : fixture.documents;

const api = {
  getAll: async (path) => ({
    "/api/correspondents/": fixture.correspondents,
    "/api/document_types/": fixture.document_types,
    "/api/tags/": fixture.tags,
    "/api/storage_paths/": fixture.storage_paths,
    "/api/custom_fields/": fixture.custom_fields,
    "/api/saved_views/": fixture.saved_views,
  }[path]),
  get: async () => ({ count: docs.length, next: null, results: docs }),
  getNext: async () => { throw new Error("the fixture is one page"); },
};

(async () => {
  const out = {};
  for (const name of Object.keys(cases)) {
    const config = Object.assign({ base_url: fixture.base_url, formats: ["csv", "json", "jsonl"] },
                                 cases[name]);
    try {
      const answer = await ENGINE.runExport(api, config,
        { stamp: "STAMP_HERE", elapsed: "ELAPSED_HERE" });
      const files = {};
      for (const f of answer.files) files[f.name] = f.text;
      const trailer = {};
      for (const k of Object.keys(answer.trailer)) {
        if (k !== "generated" && k !== "elapsed") trailer[k] = String(answer.trailer[k]);
      }
      files["_trailer"] = JSON.stringify(trailer, Object.keys(trailer).sort());
      out[name] = files;
    } catch (err) {
      out[name] = { _error: err.message };
    }
  }
  process.stdout.write(JSON.stringify(out));
})();
""".replace("STAMP_HERE", STAMP).replace("ELAPSED_HERE", ELAPSED)


def js_run(cases: dict, which: str = "normal") -> dict[str, dict[str, str]]:
    with tempfile.TemporaryDirectory() as td:
        engine = Path(td) / "engine.js"
        engine.write_text(engine_source(), encoding="utf-8")
        drive = Path(td) / "drive.js"
        drive.write_text(DRIVER, encoding="utf-8")
        payload = Path(td) / "cases.json"
        payload.write_text(json.dumps(cases), encoding="utf-8")
        proc = subprocess.run(
            [NODE, str(drive), str(engine), str(HERE / "fixture_v10.json"), str(payload),
             which],
            capture_output=True, text=True, encoding="utf-8", timeout=120)
        if proc.returncode != 0:
            raise AssertionError(f"node failed: {proc.stderr[-2000:]}")
        return json.loads(proc.stdout)


@unittest.skipUnless(NODE, "node is not installed: the JavaScript engine cannot be run here")
class TestConformance(unittest.TestCase):
    """One node run for every case: node starts slowly and the fixture is small."""

    @classmethod
    def setUpClass(cls):
        cls.js = js_run(CASES)
        cls.py = {name: python_run(case) for name, case in CASES.items()}
        cls.js_hostile = js_run(CASES, "hostile")
        cls.py_hostile = {name: python_run(case, docs=HOSTILE) for name, case in CASES.items()}

    def _case(self, name, hostile=False):
        js = (self.js_hostile if hostile else self.js)[name]
        self.assertNotIn("_error", js,
                         f"the JavaScript engine refused case {name}: {js.get('_error')}")
        py = (self.py_hostile if hostile else self.py)[name]
        for filename in sorted(py):
            self.assertIn(filename, js, f"{name}: the page wrote no {filename}")
            if filename == "_trailer":
                # The trailer is compared as values, not as one runtime's idea of spacing.
                self.assertEqual(json.loads(py[filename]), json.loads(js[filename]), name)
                continue
            expected, got = py[filename], normalise(js[filename])
            if expected != got:
                for i, (a, b) in enumerate(zip(expected, got)):
                    if a != b:
                        near = max(0, i - 60)
                        self.fail(f"{name}/{filename} differs at byte {i}\n"
                                  f"  python: {expected[near:i + 60]!r}\n"
                                  f"  page:   {got[near:i + 60]!r}")
                self.fail(f"{name}/{filename} differs in length: "
                          f"python {len(expected)}, page {len(got)}")
        for filename in sorted(js):
            self.assertIn(filename, py, f"{name}: the page wrote {filename} and the CLI did not")


for _name in CASES:
    setattr(TestConformance, f"test_{_name}", lambda self, n=_name: self._case(n))
    setattr(TestConformance, f"test_{_name}_hostile",
            lambda self, n=_name: self._case(n, hostile=True))


@unittest.skipUnless(NODE, "node is not installed: the JavaScript engine cannot be run here")
class TestUnknownConfigKey(unittest.TestCase):
    """A `tags` key at the top level, instead of nested under `filters`, once exported the whole
    archive with no filter and no error — normaliseConfig silently dropped it. Both engines now
    refuse an unknown key rather than drop it."""

    def test_a_misplaced_filter_key_is_refused_not_silently_dropped(self):
        out = js_run({"misplaced": {"tags": ["tax"]}})["misplaced"]
        self.assertIn("_error", out, "the engine wrote a sheet instead of refusing")
        self.assertEqual(out["_error"], "unknown setting(s): tags")

    def test_the_message_shape_matches_the_servers_own_refusal(self):
        """Same words, same key set style, whichever engine ran."""
        import paperless_serve as srv
        with self.assertRaises(srv.BadRequest) as cm:
            srv.argv_from_config({"bogus": True}, Path("/tmp"), insecure=False)
        self.assertEqual(str(cm.exception), "unknown setting(s): bogus")
        out = js_run({"bogus": {"bogus": True}})["bogus"]
        self.assertEqual(out["_error"], "unknown setting(s): bogus")

    def test_two_unknown_keys_are_both_named_sorted(self):
        out = js_run({"two": {"tags": ["x"], "aardvark": True}})["two"]
        self.assertEqual(out["_error"], "unknown setting(s): aardvark, tags")


if __name__ == "__main__":
    unittest.main()
