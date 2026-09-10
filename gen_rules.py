#!/usr/bin/env python3
"""The saved-view rule map has one source: RULE_MAP in paperless_export.py.

The JavaScript engine in the page carries a generated copy; this checks the copy against the
source and can regenerate it. A map corrected in one place and left stale in the other exports a
saved view as something the user is not looking at, and it reconciles while doing it.

    python3 execution/gen_rules.py           check, exit 1 on drift
    python3 execution/gen_rules.py --write   regenerate the block in paperless_front.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import paperless_export as px  # noqa: E402

HERE = Path(__file__).resolve().parent
PAGE_FILE = HERE / "paperless_front.py"
START = "// ---- RULE MAP: generated from paperless_export.py, do not edit by hand ----"
END = "// ---- END RULE MAP ----"


def find_ship_doc(rel_path: str, start: Path) -> Path | None:
    """A document such as README.md that sits beside the modules in the flat public repo, but one
    level up from execution/ in this project's own layout. Beside first, so the ship tree finds it;
    then one level up, so this project's own layout does. None if neither has it. One
    implementation so the three places that need a ship doc (TestVersion, the README-CORS test,
    the front 2 batter) cannot resolve it three different ways and die three different ways in the
    flat layout.
    """
    beside = start / rel_path
    if beside.is_file():
        return beside
    above = start.parent / rel_path
    if above.is_file():
        return above
    return None


def rules_block() -> str:
    rules = {str(k): [v[0], v[1], v[2]] for k, v in sorted(px.RULE_MAP.items())}
    return (f"{START}\n"
            f"const RULE_MAP = {json.dumps(rules, indent=0).replace(chr(10), ' ')};\n"
            f"const VIEW_FIELD_MAP = {json.dumps(px.VIEW_FIELD_MAP, indent=0).replace(chr(10), ' ')};\n"
            f"{END}")


def check() -> list[str]:
    """The page against the code. A private reference table this project keeps for itself carries
    a second check, against this same RULE_MAP, that runs outside this file and never ships."""
    problems = []
    page = PAGE_FILE.read_text(encoding="utf-8")
    block = rules_block()
    if block not in page:
        problems.append(f"{PAGE_FILE.name}: the generated rule map block is missing or stale "
                        f"(run: python3 execution/gen_rules.py --write)")
    return problems


def write() -> None:
    page = PAGE_FILE.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    if not pattern.search(page):
        raise SystemExit(f"{PAGE_FILE.name} has no rule map block to replace")
    PAGE_FILE.write_text(pattern.sub(lambda _m: rules_block(), page), encoding="utf-8")
    print(f"wrote the rule map into {PAGE_FILE.name}")


if __name__ == "__main__":
    if "--write" in sys.argv[1:]:
        write()
        sys.exit(0)
    found = check()
    for line in found:
        print(line, file=sys.stderr)
    print("rule map: one source, no drift" if not found else f"{len(found)} problem(s)")
    sys.exit(1 if found else 0)
