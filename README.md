# paperless-export

Export a [paperless-ngx](https://docs.paperless-ngx.com) document list to a sheet you can check.

One command against your own instance gives you a CSV, XLSX, JSON or JSONL of exactly the
documents a filter or a saved view shows on screen — custom fields included, totals if you want
them, and the matching PDFs beside the sheet if you ask for them.

Every run ends with a line that says how many rows it wrote and how many documents the API said
there were. If those two numbers disagree the export fails. A sheet you cannot check is worse than
no sheet.

Read-only. Nothing is uploaded anywhere; the files land on your own disk.

## Install

Python 3.10 or newer.

```bash
git clone https://github.com/Ildana-ai/paperless-export.git
cd paperless-export
pipx install ".[xlsx]"
```

That puts a `paperless-export` command on your PATH. Drop `[xlsx]` if you do not need Excel
workbooks — CSV, JSON and JSONL need nothing but Python itself.

No pipx? `pip install -r requirements.txt` and run `python3 paperless_export.py` instead. Every
example below works either way.

## Point it at your instance

Two environment variables. The token is never a command-line flag, because anything on the command
line shows up in your shell history and in the process list.

```bash
export PAPERLESS_URL=https://paperless.example.com
export PAPERLESS_TOKEN=40charactertokenfromyourpaperlessprofile
```

Get the token from paperless: your user menu → **My Profile** → **API Auth Token**.

To avoid retyping them, put them in a `.env` file — a plain text file of `NAME=value` lines that
your shell reads on demand:

```
PAPERLESS_URL=https://paperless.example.com
PAPERLESS_TOKEN=40charactertokenfromyourpaperlessprofile
```

Load it with `set -a; source .env; set +a`. Keep it out of git (`echo .env >> .gitignore`) and
`chmod 600 .env` — it holds a key to every document in your archive. This tool never creates or
edits that file.

## Use it

```bash
paperless-export -o invoices --tag Invoice --created-from 2025-01-01
```

Writes `invoices.csv` and prints the trailer.

### Every flag

| Flag | What it does | Example |
|---|---|---|
| `--view` | Export a saved view exactly as it appears on screen: its filters, its sort, its columns | `--view "Tax Invoices 2025"` |
| `--query` | Full text search | `--query "electricity"` |
| `--title` | Title contains | `--title "Invoice"` |
| `--correspondent` | By correspondent, name or id; repeatable | `--correspondent "City Bank"` |
| `--document-type` | By type; repeatable | `--document-type Invoice` |
| `--tag` | By tag; repeatable, and a document must have **all** of them | `--tag Tax --tag 2025` |
| `--storage-path` | By storage path; repeatable | `--storage-path Archive` |
| `--created-from` | Created on or after | `--created-from 2025-01-01` |
| `--created-to` | Created on or before | `--created-to 2025-12-31` |
| `--custom-field-query` | paperless's own custom field query, passed through verbatim | `--custom-field-query '["Amount","gt",100]'` |
| `--sum` | Totals row for a numeric custom field; repeatable | `--sum Amount` |
| `--columns` | Pick and reorder columns | `--columns id,title,created,custom_field:Amount` |
| `--content` | Include the full OCR text column (off by default; it is large) | `--content` |
| `--locale` | `dot` (default) or `comma` for European Excel | `--locale comma` |
| `--date` | `iso` (default), `us` (`MM/DD/YYYY`), `eu` (`DD.MM.YYYY`), or any strftime pattern | `--date eu` |
| `--headers` | `readable` column headings (`Archive serial number`) or `raw` (`archive_serial_number`). Readable is the default for csv and xlsx, raw for json and jsonl | `--headers raw` |
| `--list-sep` | What joins a multi-value cell such as tags. Default `"; "` | `--list-sep " \| "` |
| `-o`, `--output` | Output path, without an extension | `-o ~/Documents/invoices` |
| `--format` | `csv`, `json`, `jsonl`, `xlsx`; repeatable, all written in one run | `--format csv --format xlsx` |
| `--pack` | Also download the matching PDFs into a dated folder beside the sheet | `--pack` |
| `--pack-version` | `latest` (default) or `original` file version | `--pack-version original` |
| `--inventory` | Also write a print-ready HTML sheet ordered by ASN, for the front of a binder | `--inventory` |
| `--insecure` | Allow plain http to a public host. See below | `--insecure` |
| `--serve` | Open the same export as a form in your browser, on `127.0.0.1` only. See below | `--serve` |
| `--idle` | `--serve` only: end the session after this long with no activity. Default 900, minimum 60 | `--idle 300` |
| `--no-open` | `--serve` only: print the link instead of opening a browser | `--no-open` |
| `--version` | Print the version and exit. Needs no environment and no instance | `--version` |

### The trailer

```
rows written   : 42
api count      : 42
filter         : tags__id__all=3&created__date__gte=2025-01-01
formats        : csv, xlsx
headers        : readable
date format    : iso
list separator : '; '
generated      : 2026-01-31T09:14:02
elapsed        : 1.8s
```

`rows written` is how many rows are in your sheet. `api count` is how many documents paperless said
match that filter. **They must be equal.** If they are not, the export exits `3` and tells you the
sheet is not trustworthy — usually because something was writing to the instance while it ran.
Re-run it when the instance is quiet.

`headers`, `date format` and `list separator` record how the sheet was rendered, so a file you find
six months later says what produced it. `headers` is per file: csv and xlsx say `readable`, json and
jsonl say `raw`, unless you passed `--headers`.

Anything the tool had to fudge — a select option with no label, a saved-view column it could not
place — is named in the trailer too. It never blanks a value silently.

Exit codes: `0` fine, `1` failed, `2` bad invocation, `3` the sheet did not reconcile.

### Saved views

```bash
paperless-export --view "Tax Invoices 2025" -o tax-2025 --format xlsx
```

What is on screen is what you get: the view's filters, its sort order, its columns. `--view` carries
its own filters, so it cannot be combined with the filter flags.

If your paperless version has a filter rule this tool does not know, it stops and names the rule
number instead of quietly dropping that filter — a dropped filter gives you a sheet with too many
rows that still reconciles against its own count, which is the one failure worth refusing.

### Totals

```bash
paperless-export --tag Invoice --sum Amount -o invoices --format xlsx
```

Adds a `TOTAL` row. Works on integer, float and monetary fields. If a monetary field mixes
currencies it refuses rather than adding dollars to euros.

### European Excel

```bash
paperless-export --locale comma -o rechnungen
```

Semicolon separator, comma decimal mark. Excel in a European locale will not open a comma-separated
CSV without a fight; this is the fix.

### The whole packet

```bash
paperless-export --tag Tax --created-from 2025-01-01 --pack -o tax-2025 --format xlsx
```

`tax-2025.xlsx` plus `tax-2025-2026-01-31/` holding every matching PDF, and a `file` column in the
sheet with the relative path to each one. Hand the folder to your accountant and the sheet points
into it. A `file:version` column records whether you packed the latest or the original file.

### Binder sheet

```bash
paperless-export --storage-path Archive --inventory -o archive
```

`archive.inventory.html` — open it, print it, put it in the front of the binder. Ordered by archive
serial number; documents without one are listed at the end.

## In a browser, without changing your instance

```bash
paperless-export --serve
```

The same export, as a form. The command serves one page on `127.0.0.1`, prints a link, and opens
it:

```
paperless-export 0.4.0 - one session, 127.0.0.1 only, no CORS change needed
  http://127.0.0.1:54463/?s=MNJlakT7Te8XqH7B9P1l6v79IsnFqtsSTC_QDoBUn6k
  files land in /home/you/paperless-export-<date-time>
  the link works once; it dies on Ctrl-C, on Quit, or after 900s idle
```

Fill the form, press Run, and the page shows the same trailer the terminal prints and links the
files it just wrote. Each run gets its own dated folder, readable only by you. Running again links
the new run instead; the earlier files stay where they were written. A run the tool refuses — a
setting it will not take — changes nothing: the previous run's links keep working.

**Your token never enters the browser.** The page has no field for it and never receives it: the
export runs in the command you started, exactly as it would from the terminal. That is why this
needs no `PAPERLESS_CORS_ALLOWED_HOSTS` and no change of any kind on your paperless instance.

**One session, one link.** The link carries a session key that works exactly once. The page takes
it out of the address bar the moment it loads, so it is not left in your browser history, and a
copy of the link opens nothing.

**A reload ends the session.** The key is only in the page, so pressing reload leaves the page with
nothing and it will tell you so. Nothing is lost but the form — the files of a finished run are
already on disk. Press Ctrl-C and run the command again.

**It shuts itself down** on Ctrl-C, on the page's Quit button, or after 15 minutes with no
activity. `--idle SECONDS` changes that (60 at the least; it cannot be switched off).
`--no-open` prints the link instead of opening a browser.

Any export flag you pass alongside `--serve` becomes the form's starting value, so
`paperless-export --serve --tag Invoice --format xlsx` opens with those already filled in.

The port is `127.0.0.1` and only `127.0.0.1`. There is no flag to put it on your network, and
there will not be one: the session key travels in the clear.

## In a browser, on a machine that has no Python

`paperless-export.html` is a single file. Copy it anywhere, open it, and it talks to your paperless
from the browser. Nothing is installed and nothing runs in the background. If you have the tool,
you can write the file yourself:

```bash
python -m paperless_front paperless-export.html
```

**This one needs a change on your paperless.** A browser will not let a page read another site
unless that site says so, so your instance has to name the address this page is served from:

```bash
python3 -m http.server 9001     # in the folder holding the file, then open http://localhost:9001
```

and on the machine running paperless, set

```
PAPERLESS_CORS_ALLOWED_HOSTS=http://localhost:9001
```

and restart it. That names one origin — the one you just served the file from — and nothing else.

**If you open the file directly instead** (`file:///...`), its origin is the word `null`, and the
only setting that matches is `PAPERLESS_CORS_ALLOWED_HOSTS=null`. It works, and it is worth knowing
what it does: `null` is also the origin of every sandboxed frame on the web, and paperless allows
credentials and every method to an allowed origin. While that setting is in place, any page you
visit, in a browser that is logged into paperless, can read your archive and delete from it. Use
the served-from-an-origin route above if you can, and if you do use `null`, take it out when you
are done.

**Your token is typed into the page and stays in the tab.** It is never saved, never put in the
address, never written to storage, and closing the tab is the end of it. That is also the honest
limit of this front: a browser is a busier place than a terminal, and an extension with permission
to read your pages can read the token out of it. On a machine that has the tool installed,
`--serve` keeps the token out of the browser entirely.

**What it writes:** `csv`, `json`, `jsonl` and the inventory sheet, with the same columns, the same
guards and the same trailer as the command line — held to that by a test that compares both, byte
for byte. `xlsx` and `--pack` are command-line only: both mean building a zip inside the tab, in
memory, with no way to stream it to disk in every browser. For a European-Excel CSV, pick the
`;` separator, which is what it was for.

## http and https

Plain `http` is allowed to your own network — loopback, a private address, a `.local` name, or a
hostname that resolves only to private addresses — with a one-line note, because your browser
already sends the same token over the same wire. To a public host it is refused, because that puts
your token on the open internet in the clear; `--insecure` overrides that if you know exactly what
you are doing.

https certificates are verified and there is no flag to turn that off. Redirects that leave your
instance are refused outright: a redirect carries the `Authorization` header with it, and your token
does not go to hosts you did not name.

## Why not paperless's own exporter

`document_exporter` is a whole-archive migration dump: everything, no filters, in paperless's own
format, meant for moving an instance. This is the other thing — a filtered, human-readable sheet of
the documents you asked for, with your custom fields as columns, for handing to somebody.

## Licence

MIT.
