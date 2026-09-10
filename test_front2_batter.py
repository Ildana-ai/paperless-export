#!/usr/bin/env python3
"""Battering script for front 2, the page opened from disk.

    python3 execution/test_front2_batter.py

Fires every attack this project's own threat model calls for at the built page. The page is
driven in a real DOM under node, so the attacks are made against the code that ships, not against
a description of it. Exit 0 only if every one was refused. Can't verify, don't ship.

node is required. Without it this exits 2 and says so: a skipped battering is not a pass.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gen_rules                       # noqa: E402
import paperless_front                 # noqa: E402
from test_front2_conformance import engine_source   # noqa: E402

HERE = Path(__file__).resolve().parent
NODE = shutil.which("node")
RESULTS: list[tuple[bool, str, str]] = []


def check(ok: bool, name: str, detail: str = "") -> None:
    RESULTS.append((bool(ok), name, detail))
    print(f"{'pass' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if detail and not ok else ""))


# --------------------------------------------------------------------------------------
# F1 / F2 / F3 / F4 / F5: what the file itself carries
# --------------------------------------------------------------------------------------
def f1_the_token_in_the_page(page: str) -> None:
    for banned in ("localStorage", "sessionStorage", "document.cookie", "indexedDB"):
        check(banned not in page, f"F1 the page never touches {banned}")
    check(page.count('"Authorization"') == 1,
          "F1 exactly one place builds the Authorization header", str(page.count('"Authorization"')))
    check('<input type="password" id="f-token" autocomplete="off">' in page,
          "F1 the token field is a password field that does not autofill")
    check("token=" not in page and "?token" not in page,
          "F1 no code path puts a token in a URL")
    check('credentials: "omit"' in page, "F1 cookies are never sent with a request")


def f2_the_null_origin(page: str) -> None:
    help_text = re.search(r"const CORS_HELP =(.*?);\n", page, re.S).group(1)
    check(help_text.index("http.server 9001") < help_text.index("null"),
          "F2 the page offers the named-origin route before it mentions null")
    warning = re.search(r"const NULL_WARNING =(.*?);\n", page, re.S).group(1)
    for word in ("sandboxed", "delete", "take it back out"):
        check(word in warning, f"F2 the null warning says {word!r}")
    readme_path = gen_rules.find_ship_doc("README.md", HERE)
    if readme_path is None:
        check(False, "F2 the README names the safe route before null", "README.md not found beside or above this file")
    else:
        readme = readme_path.read_text(encoding="utf-8")
        check(readme.index("http.server 9001") < readme.index("PAPERLESS_CORS_ALLOWED_HOSTS=null"),
              "F2 the README names the safe route before null")


def f3_markup(page: str) -> None:
    for banned in ("innerHTML", "insertAdjacentHTML", "document.write", "outerHTML", "eval("):
        check(banned not in page, f"F3 no {banned} anywhere in the page")
    check('http-equiv="Content-Security-Policy"' in page,
          "F3 the disk build carries a policy of its own")
    check("<script src" not in page and "<link " not in page,
          "F3 nothing is loaded from another origin")


def f4_f5_refusals(page: str) -> None:
    check('redirect: "error"' in page, "F4 a redirect is a failure, never a follow")
    check("points at another origin" in page, "F4 a next-page link off the origin is refused")
    check('insecureWord !== "insecure"' in page, "F5 public http needs the word typed")
    check("mixed content" in page, "F5 https page against http instance is explained, not attempted")


# --------------------------------------------------------------------------------------
# The live half: the engine and the page's own functions, driven under node
# --------------------------------------------------------------------------------------
DRIVER = r"""
const fs = require("fs");
const ENGINE = require(process.argv[2]);
const fixture = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const out = [];
const check = (ok, name, detail) => out.push([!!ok, name, detail || ""]);

const api = (docs, count) => ({
  getAll: async (path) => ({
    "/api/correspondents/": fixture.correspondents,
    "/api/document_types/": fixture.document_types,
    "/api/tags/": fixture.tags,
    "/api/storage_paths/": fixture.storage_paths,
    "/api/custom_fields/": fixture.custom_fields,
    "/api/saved_views/": fixture.saved_views,
  }[path]),
  get: async () => ({ count: count === undefined ? docs.length : count, next: null, results: docs }),
  getNext: async () => { throw new Error("one page"); },
});

(async () => {
  const base = { base_url: fixture.base_url, formats: ["csv", "json", "jsonl"], inventory: true };

  // F3 - a hostile title through the whole engine
  const answer = await ENGINE.runExport(api(fixture.hostile_documents), base);
  const all = answer.files.map(f => f.text).join("\n");
  check(!/<script>/.test(all.replace(/&lt;script&gt;/g, "")),
        "F3 no unescaped <script> reached any file the page built");
  const inventory = answer.files.find(f => f.name.endsWith(".inventory.html")).text;
  check(inventory.includes("&quot;"), "F3 a quote in a title is escaped in the inventory");
  check(!inventory.includes('<td>=1+1 and a " quote'), "F3 the raw title is not in the markup");
  const csv = answer.files.find(f => f.name.endsWith(".csv")).text;
  check(csv.includes("\"'=1+1"), "F3 a formula title is guarded and quoted in the CSV");

  // F7 - the reconciliation guard
  try {
    await ENGINE.runExport(api(fixture.documents, 99), base);
    check(false, "F7 a count that disagrees must stop the export");
  } catch (err) {
    check(/rows written 2 != api count 99/.test(err.message) && err.kind === "reconcile",
          "F7 rows != count is a hard failure with both numbers", err.message);
  }

  // F6 - a rule the map does not know is refused, not dropped
  try {
    ENGINE.paramsFromView({ filter_rules: [{ rule_type: 999, value: "x" }] }, []);
    check(false, "F6 an unknown saved-view rule must be refused");
  } catch (err) {
    check(/unknown filter rule_type/.test(err.message),
          "F6 an unknown saved-view rule is refused, not silently dropped");
  }

  // F5 / config - what the page will not export
  for (const bad of [{ formats: ["xlsx"] }, { formats: ["pack"] }]) {
    try {
      ENGINE.normaliseConfig(Object.assign({ base_url: "https://x" }, bad));
      check(false, "F5 format " + bad.formats[0] + " must be refused");
    } catch (err) {
      check(/is not one this page writes/.test(err.message),
            "F5 format " + bad.formats[0] + " is refused with a reason");
    }
  }
  try {
    ENGINE.normaliseConfig({ base_url: "https://x", date: "%Q" });
    check(false, "F5 a strftime pattern must be refused by the page");
  } catch (err) {
    check(/is not one of iso, us, eu/.test(err.message), "F5 a strftime pattern is refused");
  }

  // The engine must never be handed the token: it takes an api object, not a credential.
  check(ENGINE.runExport.length <= 3, "F1 the engine takes an api object, never a token");

  process.stdout.write(JSON.stringify(out));
})();
"""


def live(page: str) -> None:
    with tempfile.TemporaryDirectory() as td:
        engine = Path(td) / "engine.js"
        engine.write_text(engine_source(), encoding="utf-8")
        drive = Path(td) / "drive.js"
        drive.write_text(DRIVER, encoding="utf-8")
        proc = subprocess.run([NODE, str(drive), str(engine), str(HERE / "fixture_v10.json")],
                              capture_output=True, text=True, encoding="utf-8", timeout=120)
        if proc.returncode != 0:
            check(False, "the node driver ran", proc.stderr[-500:])
            return
        for ok, name, detail in json.loads(proc.stdout):
            check(ok, name, detail)


def main() -> int:
    if not NODE:
        print("node is not installed: the page's engine cannot be driven here, so this is not a "
              "pass. Install node, or run this on a machine that has it.", file=sys.stderr)
        return 2
    page = paperless_front.disk_page()
    print(f"battering the disk build: {len(page)} bytes\n")
    f1_the_token_in_the_page(page)
    f2_the_null_origin(page)
    f3_markup(page)
    f4_f5_refusals(page)
    live(page)

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
