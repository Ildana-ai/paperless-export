# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/2.0.0/).

## [Unreleased]

## [0.4.0] - 2026-09-11

### Added

- `paperless-export`, a command line tool that reads a paperless-ngx instance over its own API and
  writes a sheet of the matching documents: csv, json, jsonl, xlsx, repeatable and all written in
  one run.
- `--view <id|name>` exports a saved view exactly as it appears on screen — its filters, its sort
  order, its display columns — mapped through all 51 of paperless's filter rule types.
- Filters without a view: full text, title, correspondent, document type, tag, storage path,
  created-from / created-to, and paperless's own `custom_field_query`.
- Custom fields are read from the instance at run time, one column per field in the instance's own
  order, every field type paperless supports. Monetary fields get a value column and a currency
  column; select fields show their label.
- `--sum <field>`, repeatable, adds a totals row for a numeric custom field.
- `--locale comma` writes `;`-separated, comma-decimal output for European Excel. CSV carries a
  UTF-8 BOM and CRLF so Excel, Numbers and LibreOffice all open it without a wizard; every other
  format is LF-only on every platform.
- `--headers readable|raw` (readable by default for csv/xlsx, raw by default for json/jsonl),
  `--date iso|us|eu|<strftime>`, and `--list-sep` for multi-value cells such as tags. Presentation
  is adjustable; the formula guard and the row-count check never are.
- `--pack` downloads the matching PDFs into a dated folder beside the sheet, latest or original
  version, and adds a `file` column with a forward-slash path to each one on every platform.
- `--inventory` writes a print-ready HTML sheet ordered by archive serial number, for the front of
  a binder.
- `--columns` picks and reorders columns; `--content` adds the OCR text, off by default.
- Every run ends with a trailer — rows written, the API's own count, the filter used, the formats,
  the presentation settings, the clock — and **the row count must equal the API's own count or the
  run fails**. The tool never emits output it cannot check against the instance itself.
- Read-only: no endpoint that writes is ever called. A row is always a root document, never a file
  version's own record.
- The API token is read from the environment only, never a flag, never a URL, and is scrubbed from
  any message the tool prints.
- Plain http is allowed to a private host — including a bare LAN name that resolves to a private
  address — with a warning; a public host needs `--insecure`. A redirect off the instance you named
  is refused, because the token travels with a redirect.
- Spreadsheet formula injection is guarded in csv and xlsx; a value the tool itself renders (a
  number, a locale-formatted total) is never treated as bait — only text the API returned is.
  Titles are escaped in the HTML inventory and stripped of path separators in `--pack` file names.
- `--serve` runs the same export from a form in your browser: the command serves one page on
  `127.0.0.1` on a port the OS picks, prints a one-time link, and keeps your token out of the
  browser entirely — it never leaves the process. The session ends on Ctrl-C, the page's Quit
  button, or an idle timeout (`--idle SECONDS`, minimum 60, default 900); `--no-open` prints the
  link instead of opening a browser. Each run writes into its own dated folder and the page links
  what it wrote; a run refused before it starts leaves the previous run's links working.
- `python -m paperless_front paperless-export.html` writes a single page that talks to your
  paperless straight from the browser, with no install and nothing running in the background. It
  writes csv, json, jsonl and the inventory with the same columns, guards and trailer as the
  command line; xlsx and `--pack` stay on the command line, since both need a zip a browser tab
  cannot safely build. This page needs `PAPERLESS_CORS_ALLOWED_HOSTS` set on your instance — serve
  it from an origin you control and name that origin; opening it directly from disk also works
  with the value `null`, and the README explains plainly what that opens up.
- Exit codes: 0 complete and reconciled, 1 failed, 2 bad invocation, 3 reconciliation mismatch.
- Verified on macOS, Ubuntu and Windows against paperless-ngx 3.1.3 (API v10), Python 3.10 and
  newer (tested to 3.14), byte-identical output across all three operating systems and both the
  command line and the browser page.

[Unreleased]: https://github.com/Ildana-ai/paperless-export/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/Ildana-ai/paperless-export/releases/tag/v0.4.0
