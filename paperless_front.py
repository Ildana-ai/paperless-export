#!/usr/bin/env python3
"""The page. One page, two transports: served over a loopback session (front 3) or opened from
disk (front 2), decided at build time by one constant.

It lives in a module and not in an .html because pyproject.toml ships py-modules, which installs
.py files and nothing else; an .html beside them would not survive a pipx install. Keeping it here
makes the served page (front 3) and the disk page (front 2) the same bytes by construction.

    python -m paperless_front front.html    writes the disk copy

`{nonce}` is the only placeholder. Everything else is literal, so `PAGE.format` is never needed
anywhere but the CSP nonce.
"""
from __future__ import annotations

import sys

NONCE_MARK = "__CSP_NONCE__"

PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>paperless-export</title>
<style nonce="__CSP_NONCE__">
:root { color-scheme: light dark; }
body { font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; margin: 0; padding: 1.5rem;
       max-width: 60rem; }
h1 { font-size: 1.15rem; margin: 0 0 .25rem; }
p.sub { margin: 0 0 1.25rem; opacity: .7; }
fieldset { border: 1px solid rgba(128,128,128,.4); border-radius: 6px; margin: 0 0 1rem; padding: .75rem 1rem 1rem; }
legend { padding: 0 .35rem; font-weight: 600; font-size: .85rem; text-transform: uppercase; letter-spacing: .04em; opacity: .75; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr)); gap: .75rem 1.25rem; }
label { display: block; font-size: .85rem; margin-bottom: .15rem; opacity: .85; }
input[type=text], select, textarea { width: 100%; box-sizing: border-box; padding: .35rem .5rem;
       font: inherit; font-size: .9rem; border: 1px solid rgba(128,128,128,.5); border-radius: 4px;
       background: transparent; color: inherit; }
textarea { resize: vertical; min-height: 2.2rem; }
.checks { display: flex; flex-wrap: wrap; gap: .35rem 1.1rem; align-items: center; }
.checks label { display: inline-flex; align-items: center; gap: .35rem; margin: 0; }
button { font: inherit; padding: .45rem 1.1rem; border-radius: 5px; border: 1px solid rgba(128,128,128,.5);
       background: transparent; color: inherit; cursor: pointer; }
button.primary { font-weight: 600; }
button:disabled { opacity: .5; cursor: default; }
.bar { display: flex; gap: .6rem; align-items: center; margin-bottom: 1.25rem; }
.msg { padding: .6rem .8rem; border-radius: 5px; border: 1px solid rgba(128,128,128,.5); margin-bottom: 1rem;
       white-space: pre-wrap; }
.msg.bad { border-color: #b3261e; }
table { border-collapse: collapse; font-size: .88rem; }
th, td { text-align: left; padding: .2rem .9rem .2rem 0; vertical-align: top; }
th { font-weight: 600; opacity: .7; white-space: nowrap; }
ul.files { list-style: none; padding: 0; margin: .4rem 0 0; }
ul.files li { padding: .1rem 0; font-size: .88rem; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .85em; }
.hidden { display: none; }
/* No style="" attributes anywhere: a CSP nonce does not cover an inline style attribute, and
   default-src 'none' blocks it. Found in a browser, not in a test. */
.gap-wide { margin-top: .75rem; }
.gap { margin-top: .6rem; }
</style>
</head>
<body>
<h1>paperless-export</h1>
<p class="sub" id="sub">starting</p>

<div id="notice" class="msg hidden"></div>

<form id="connect" class="hidden">
  <fieldset><legend>Your paperless</legend>
    <div class="grid">
      <div>
        <label for="f-url">Address (https://paperless.example)</label>
        <input type="text" id="f-url" autocomplete="off" spellcheck="false">
      </div>
      <div>
        <label for="f-token">API token</label>
        <input type="password" id="f-token" autocomplete="off">
      </div>
    </div>
    <div class="gap hidden" id="insecure-wrap">
      <label for="f-insecure">That is plain http to a public address, so the token travels in
        the clear. Type the word <code>insecure</code> to do it anyway.</label>
      <input type="text" id="f-insecure" autocomplete="off">
    </div>
    <div class="bar gap">
      <button type="submit" class="primary">Connect</button>
      <span id="cstatus"></span>
    </div>
  </fieldset>
</form>

<form id="form" class="hidden">
  <fieldset><legend>What to export</legend>
    <div class="grid" id="g-filters"></div>
  </fieldset>
  <fieldset><legend>How it should read</legend>
    <div class="grid" id="g-style"></div>
  </fieldset>
  <fieldset><legend>What to write</legend>
    <div class="grid" id="g-output"></div>
    <div class="checks gap-wide" id="g-formats"></div>
    <div class="checks gap" id="g-extras"></div>
  </fieldset>
  <div class="bar">
    <button type="submit" class="primary" id="run">Run the export</button>
    <button type="button" id="quit">Quit</button>
    <span id="status"></span>
  </div>
</form>

<div id="result"></div>

<script nonce="__CSP_NONCE__">
// ---- ENGINE START ----
// The export, in the browser. The Python engine in paperless_export.py is the other one, and
// test_front2_conformance.py holds them to the same bytes. Nothing here may drift on its own.
"use strict";

// ---- RULE MAP: generated from paperless_export.py, do not edit by hand ----
const RULE_MAP = { "0": [ "title__icontains", null, false ], "1": [ "content__icontains", null, false ], "2": [ "archive_serial_number", null, false ], "3": [ "correspondent__id", "correspondent__isnull", false ], "4": [ "document_type__id", "document_type__isnull", false ], "5": [ "is_in_inbox", null, false ], "6": [ "tags__id__all", null, true ], "7": [ "is_tagged", null, false ], "8": [ "created__date__lt", null, false ], "9": [ "created__date__gt", null, false ], "10": [ "created__year", null, false ], "11": [ "created__month", null, false ], "12": [ "created__day", null, false ], "13": [ "added__date__lt", null, false ], "14": [ "added__date__gt", null, false ], "15": [ "modified__date__lt", null, false ], "16": [ "modified__date__gt", null, false ], "17": [ "tags__id__none", null, true ], "18": [ "archive_serial_number__isnull", null, false ], "19": [ "title_content", null, false ], "20": [ "query", null, false ], "21": [ "more_like_id", null, false ], "22": [ "tags__id__in", null, true ], "23": [ "archive_serial_number__gt", null, false ], "24": [ "archive_serial_number__lt", null, false ], "25": [ "storage_path__id", "storage_path__isnull", false ], "26": [ "correspondent__id__in", null, true ], "27": [ "correspondent__id__none", null, true ], "28": [ "document_type__id__in", null, true ], "29": [ "document_type__id__none", null, true ], "30": [ "storage_path__id__in", null, true ], "31": [ "storage_path__id__none", null, true ], "32": [ "owner__id", null, false ], "33": [ "owner__id__in", null, true ], "34": [ "owner__isnull", null, false ], "35": [ "owner__id__none", null, true ], "36": [ "custom_fields__icontains", null, false ], "37": [ "shared_by__id", null, true ], "38": [ "custom_fields__id__all", null, true ], "39": [ "custom_fields__id__in", null, true ], "40": [ "custom_fields__id__none", null, true ], "41": [ "has_custom_fields", null, false ], "42": [ "custom_field_query", null, false ], "43": [ "created__date__lte", null, false ], "44": [ "created__date__gte", null, false ], "45": [ "added__date__lte", null, false ], "46": [ "added__date__gte", null, false ], "47": [ "mime_type", null, false ], "48": [ "title_search", null, false ], "49": [ "text", null, false ], "50": [ "has_duplicates", null, false ] };
const VIEW_FIELD_MAP = { "title": "title", "created": "created", "added": "added", "modified": "modified", "tag": "tags", "correspondent": "correspondent", "documenttype": "document_type", "storagepath": "storage_path", "note": "notes", "owner": "owner", "shared": "shared", "asn": "archive_serial_number", "pagecount": "page_count" };
// ---- END RULE MAP ----

const DEFAULT_COLUMNS = ["id", "title", "archive_serial_number", "correspondent", "document_type",
  "tags", "storage_path", "created", "added", "modified", "original_file_name",
  "archived_file_name", "page_count", "mime_type", "notes", "versions"];
const SUMMABLE = ["integer", "float", "monetary"];
const INJECTION_PREFIXES = ["=", "+", "-", "@", "\t", "\r"];
const DATE_PRESETS = { iso: "%Y-%m-%d", us: "%m/%d/%Y", eu: "%d.%m.%Y" };
const PAGE_SIZE = 1000;

function UsageError(message) { const e = new Error(message); e.kind = "usage"; return e; }
function ExportError(message) { const e = new Error(message); e.kind = "export"; return e; }
function ReconcileError(message) { const e = new Error(message); e.kind = "reconcile"; return e; }

// A number Python would hold as a float. Python prints 10.0 where JavaScript prints 10, so the
// float-ness travels with the value instead of being guessed at from its digits.
class F {
  constructor(value) { this.v = value; }
}
function isF(x) { return x instanceof F; }
function num(x) { return isF(x) ? x.v : x; }

function pyFloat(value) {
  // CPython's repr for the floats this tool produces: always a decimal point, no exponent below 1e16.
  if (!isFinite(value)) throw ExportError("a total came out as " + value);
  let s = String(value);
  if (!/[.eE]/.test(s)) s += ".0";
  return s;
}
function pyNumber(value) { return isF(value) ? pyFloat(value.v) : String(value); }

// --- Python's json.dumps(..., ensure_ascii=False), so the two engines write the same bytes -----
const JSON_ESCAPES = { '"': '\\"', "\\": "\\\\", "\n": "\\n", "\r": "\\r", "\t": "\\t",
                       "\b": "\\b", "\f": "\\f" };
function pyStr(s) {
  let out = '"';
  for (const ch of String(s)) {
    if (JSON_ESCAPES[ch] !== undefined) out += JSON_ESCAPES[ch];
    else if (ch < " ") out += "\\u" + ch.charCodeAt(0).toString(16).padStart(4, "0");
    else out += ch;
  }
  return out + '"';
}
function pyJson(value, indent, depth) {
  const pad = indent ? "\n" + " ".repeat(indent * (depth + 1)) : "";
  const shut = indent ? "\n" + " ".repeat(indent * depth) : "";
  if (value === null || value === undefined) return "null";
  if (isF(value)) return pyFloat(value.v);
  if (typeof value === "number") return String(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "string") return pyStr(value);
  // Python's separators: (', ', ': ') compact, (',', ': ') with an indent.
  const join = indent ? "," + pad : ", ";
  if (Array.isArray(value)) {
    if (!value.length) return "[]";
    return "[" + pad + value.map(v => pyJson(v, indent, depth + 1)).join(join) + shut + "]";
  }
  const keys = Object.keys(value);
  if (!keys.length) return "{}";
  const parts = keys.map(k => pyStr(k) + ": " + pyJson(value[k], indent, depth + 1));
  return "{" + pad + parts.join(join) + shut + "}";
}

// --- Python's urllib.parse.urlencode, for the filter line in the trailer ----------------------
function pyQuotePlus(s) {
  let out = "";
  for (const byte of new TextEncoder().encode(String(s))) {
    const ch = String.fromCharCode(byte);
    if (/[A-Za-z0-9_.\-~]/.test(ch)) out += ch;
    else if (ch === " ") out += "+";
    else out += "%" + byte.toString(16).toUpperCase().padStart(2, "0");
  }
  return out;
}
function pyUrlencode(params) {
  return Object.keys(params).map(k => pyQuotePlus(k) + "=" + pyQuotePlus(params[k])).join("&");
}

// --- dates -------------------------------------------------------------------------------------
function resolveDateFormat(spec) {
  const fmt = DATE_PRESETS[spec];
  if (!fmt) {
    throw UsageError("date: " + JSON.stringify(spec) + " is not one of iso, us, eu. A strftime " +
      "pattern of your own is a command-line feature; the page offers the three presets.");
  }
  return fmt;
}
function fmtDate(value, fmt) {
  if (!value) return "";
  const s = String(value);
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return s.slice(0, 10);
  const [, Y, M, D] = m;
  return fmt.replace(/%Y/g, Y).replace(/%m/g, M).replace(/%d/g, D);
}

// --- values ------------------------------------------------------------------------------------
function parseMonetary(raw) {
  if (raw === null || raw === undefined || raw === "") return ["", null];
  const m = String(raw).trim().match(/^([A-Za-z]{3})?\s*(-?[\d.,]+)$/);
  if (!m) return ["", null];
  const cur = (m[1] || "").toUpperCase();
  const value = parseFloat(m[2].replace(/,/g, ""));
  return [cur, isNaN(value) ? null : value];
}

function isFormulaBait(value) {
  return typeof value === "string" && INJECTION_PREFIXES.some(p => value.startsWith(p));
}
// Decides by the value's origin, called on the raw value before fmtNumber renders anything: a
// number the engine produced is never bait, even after the comma locale turns it into printed
// text like "-12,50". Called after fmtNumber, a rendered negative number reads as a string
// starting with "-" and gets prefixed — a European refund turned into text. Matched to the
// Python engine so the two cannot drift on this again.
function guard(value) { return isFormulaBait(value) ? "'" + value : value; }

function fmtNumber(value, cfg) {
  if (typeof value === "boolean") return value ? "true" : "false";
  if (isF(value) || typeof value === "number") {
    if (cfg.decimal === ",") return pyNumber(value).replace(".", ",");
    return value;
  }
  return value;
}

// --- headings ----------------------------------------------------------------------------------
function readableHeader(col) {
  if (col.startsWith("custom_field:")) {
    const rest = col.slice("custom_field:".length);
    return rest.endsWith(":currency") ? rest.slice(0, -":currency".length) + " currency" : rest;
  }
  const s = col.replace(/:/g, " ").replace(/_/g, " ");
  return s.slice(0, 1).toUpperCase() + s.slice(1);
}
function headerStyle(cfg, fmt) {
  if (cfg.headers) return cfg.headers;
  return (fmt === "csv" || fmt === "xlsx") ? "readable" : "raw";
}
function readableClashes(columns) {
  const labels = columns.map(readableHeader);
  const seen = new Set();
  labels.forEach(l => { if (labels.filter(x => x === l).length > 1) seen.add(l); });
  return Array.from(seen).sort();
}
function headings(columns, style) {
  if (style !== "readable") return columns.slice();
  const clash = new Set(readableClashes(columns));
  return columns.map(c => clash.has(readableHeader(c)) ? c : readableHeader(c));
}

// --- lookups -----------------------------------------------------------------------------------
class Lookups {
  constructor(data) {
    this.correspondents = new Map(data.correspondents.map(r => [r.id, r.name]));
    this.documentTypes = new Map(data.document_types.map(r => [r.id, r.name]));
    this.tags = new Map(data.tags.map(r => [r.id, r.name]));
    this.storagePaths = new Map(data.storage_paths.map(r => [r.id, r.name]));
    this.customFields = data.custom_fields;
    this.cfById = new Map(this.customFields.map(f => [f.id, f]));
  }
  resolve(table, value, what) {
    if (/^\d+$/.test(String(value))) {
      const id = parseInt(value, 10);
      if (table.has(id)) return id;
      throw UsageError("no " + what + " with id " + id);
    }
    const wanted = String(value).toLowerCase();
    const matches = [];
    table.forEach((name, id) => { if (name.toLowerCase() === wanted) matches.push(id); });
    if (matches.length === 1) return matches[0];
    if (!matches.length) {
      const near = [];
      table.forEach(name => { if (near.length < 5 && name.toLowerCase().includes(wanted)) near.push(name); });
      throw UsageError("no " + what + " named " + JSON.stringify(String(value)) +
                       "." + (near.length ? " did you mean: " + near.join(", ") + "?" : ""));
    }
    throw UsageError(what + " " + JSON.stringify(String(value)) + " is ambiguous (ids " + matches + ")");
  }
  cfColumnName(f) {
    const same = this.customFields.filter(g => g.name === f.name);
    return same.length === 1 ? "custom_field:" + f.name : "custom_field:" + f.name + "#" + f.id;
  }
}

// --- filters -----------------------------------------------------------------------------------
function paramsFromView(view, notes) {
  const multi = {};
  const params = {};
  for (const rule of view.filter_rules || []) {
    const rt = String(rule.rule_type);
    const val = rule.value;
    if (!(rt in RULE_MAP)) {
      throw ExportError("saved view uses unknown filter rule_type " + rt + ". This paperless " +
        "version added a rule this tool does not map. Refusing rather than silently dropping a " +
        "filter (that would produce a sheet with too many rows that still reconciles). " +
        "Report rule type " + rt + " to the maintainer so it can be added.");
    }
    const [param, isnullParam, isMulti] = RULE_MAP[rt];
    if (val === null || val === undefined) {
      if (isnullParam) params[isnullParam] = "true";
      continue;
    }
    if (isMulti) (multi[param] = multi[param] || []).push(String(val));
    else params[param] = String(val);
  }
  for (const param of Object.keys(multi)) params[param] = multi[param].join(",");

  let sort = null;
  if (view.sort_field) sort = (view.sort_reverse ? "-" : "") + String(view.sort_field);

  let columns = null;
  const display = view.display_fields || [];
  if (display.length) {
    columns = [];
    for (const d of display) {
      if (d in VIEW_FIELD_MAP) columns.push(VIEW_FIELD_MAP[d]);
      else if (d.startsWith("custom_field_")) columns.push(d);
      else notes.push("saved view display field '" + d + "' not recognised, column skipped");
    }
  }
  return [params, sort, columns];
}

function paramsFromFlags(cfg, lk) {
  const f = cfg.filters || {};
  const params = {};
  if (f.query) params["query"] = f.query;
  if (f.title) params["title__icontains"] = f.title;
  const named = [["correspondent", lk.correspondents, "correspondent__id__in"],
                 ["document_type", lk.documentTypes, "document_type__id__in"],
                 ["storage_path", lk.storagePaths, "storage_path__id__in"]];
  for (const [key, table, param] of named) {
    if (f[key] && f[key].length) {
      params[param] = f[key].map(v => String(lk.resolve(table, v, key))).join(",");
    }
  }
  if (f.tags && f.tags.length) {
    params["tags__id__all"] = f.tags.map(v => String(lk.resolve(lk.tags, v, "tag"))).join(",");
  }
  if (f.created_from) params["created__date__gte"] = f.created_from;
  if (f.created_to) params["created__date__lte"] = f.created_to;
  if (f.custom_field_query) params["custom_field_query"] = f.custom_field_query;
  return params;
}

// --- rows --------------------------------------------------------------------------------------
function flattenCustomFields(doc, lk, cfg, notes) {
  const out = {};
  for (const f of lk.customFields) {
    const col = lk.cfColumnName(f);
    out[col] = "";
    if (f.data_type === "monetary") out[col + ":currency"] = "";
  }
  const values = new Map((doc.custom_fields || []).map(v => [v.field, v.value]));
  for (const f of lk.customFields) {
    if (!values.has(f.id)) continue;
    const col = lk.cfColumnName(f);
    const val = values.get(f.id);
    if (val === null || val === undefined) continue;
    const type = f.data_type;
    if (type === "string" || type === "longtext" || type === "url" || type === "integer") {
      out[col] = val;
    } else if (type === "float") {
      out[col] = new F(val);
    } else if (type === "boolean") {
      out[col] = val;
    } else if (type === "date") {
      out[col] = fmtDate(val, cfg.dateFmt);
    } else if (type === "monetary") {
      const [cur, value] = parseMonetary(val);
      out[col] = value === null ? val : new F(value);
      out[col + ":currency"] = cur;
    } else if (type === "select") {
      const opts = (f.extra_data || {}).select_options || [];
      const hit = opts.find(o => o.id === val);
      if (hit === undefined) {
        out[col] = val;
        notes.push("select field '" + f.name + "': option id '" + val + "' has no label, written verbatim");
      } else {
        out[col] = hit.label;
      }
    } else if (type === "documentlink") {
      out[col] = (val || []).map(String).join(cfg.listSep);
    } else {
      out[col] = val;
      notes.push("custom field '" + f.name + "' has unknown data_type '" + type + "', written verbatim");
    }
  }
  return out;
}

function buildRow(doc, lk, cfg, notes) {
  const tags = (doc.tags || []).map(t => lk.tags.has(t) ? lk.tags.get(t) : String(t)).join(cfg.listSep);
  const row = {
    id: doc.id,
    title: doc.title || "",
    archive_serial_number: doc.archive_serial_number === null || doc.archive_serial_number === undefined
      ? "" : doc.archive_serial_number,
    correspondent: doc.correspondent ? (lk.correspondents.get(doc.correspondent) || "") : "",
    document_type: doc.document_type ? (lk.documentTypes.get(doc.document_type) || "") : "",
    tags: tags,
    storage_path: doc.storage_path ? (lk.storagePaths.get(doc.storage_path) || "") : "",
    created: fmtDate(doc.created || doc.created_date, cfg.dateFmt),
    added: fmtDate(doc.added, cfg.dateFmt),
    modified: fmtDate(doc.modified, cfg.dateFmt),
    original_file_name: doc.original_file_name || "",
    archived_file_name: doc.archived_file_name || "",
    page_count: doc.page_count === null || doc.page_count === undefined ? "" : doc.page_count,
    mime_type: doc.mime_type || "",
    notes: (doc.notes || []).length,
    versions: (doc.versions || []).length,
    owner: doc.owner === null || doc.owner === undefined ? "" : doc.owner,
    shared: doc.is_shared_by_requester === undefined ? "" : doc.is_shared_by_requester,
    file: "",
    "file:version": "",
    url: cfg.baseUrl + "/documents/" + doc.id + "/details",
  };
  if (cfg.content) row.content = doc.content || "";
  Object.assign(row, flattenCustomFields(doc, lk, cfg, notes));
  return row;
}

function resolveColumns(cfg, lk, viewColumns, notes) {
  const cfCols = [];
  for (const f of lk.customFields) {
    const col = lk.cfColumnName(f);
    cfCols.push(col);
    if (f.data_type === "monetary") cfCols.push(col + ":currency");
  }
  if (viewColumns !== null && viewColumns !== undefined) {
    const cols = [];
    for (const c of viewColumns) {
      if (c.startsWith("custom_field_")) {
        const fid = parseInt(c.slice(c.lastIndexOf("_") + 1), 10);
        if (isNaN(fid)) { notes.push("saved view column '" + c + "' unparseable, skipped"); continue; }
        const f = lk.cfById.get(fid);
        if (!f) {
          notes.push("saved view references custom field id " + fid +
                     ", which no longer exists; column skipped");
          continue;
        }
        cols.push(lk.cfColumnName(f));
        if (f.data_type === "monetary") cols.push(lk.cfColumnName(f) + ":currency");
      } else {
        cols.push(c);
      }
    }
    return cols;
  }
  if (cfg.columns && cfg.columns.length) {
    const known = new Set(DEFAULT_COLUMNS.concat(cfCols,
      ["owner", "shared", "file", "file:version", "url", "content"]));
    for (const c of cfg.columns) if (!known.has(c)) throw UsageError("unknown column '" + c + "'");
    return cfg.columns.slice();
  }
  let cols = DEFAULT_COLUMNS.concat(cfCols);
  if (cfg.content) cols.push("content");
  cols.push("url");
  return cols;
}

function totalsRow(rows, cfg, lk, columns) {
  const total = {};
  for (const c of columns) total[c] = "";
  total[columns[0]] = "TOTAL";
  for (const name of cfg.sums || []) {
    const matches = lk.customFields.filter(f => f.name.toLowerCase() === String(name).toLowerCase());
    if (!matches.length) throw UsageError("sum: no custom field named '" + name + "'");
    const f = matches[0];
    if (!SUMMABLE.includes(f.data_type)) {
      throw UsageError("sum: field '" + f.name + "' is " + f.data_type + ", not summable");
    }
    const col = lk.cfColumnName(f);
    if (!columns.includes(col)) {
      throw UsageError("sum: field '" + f.name + "' is not among the exported columns");
    }
    if (f.data_type === "monetary") {
      const currencies = new Set();
      for (const r of rows) {
        if (r[col] !== "" && r[col] !== null && r[col] !== undefined) {
          const c = r[col + ":currency"];
          if (c) currencies.add(c);
        }
      }
      if (currencies.size > 1) {
        throw ExportError("sum: field '" + f.name + "' mixes currencies " +
          JSON.stringify(Array.from(currencies).sort()) + ". Refusing a meaningless total.");
      }
      if (currencies.size === 1) total[col + ":currency"] = Array.from(currencies)[0];
    }
    let sum = 0;
    for (const r of rows) {
      const v = r[col];
      if (isF(v) || (typeof v === "number" && typeof v !== "boolean")) sum += num(v);
    }
    total[col] = f.data_type === "integer" ? Math.round(sum) : new F(Math.round(sum * 100) / 100);
  }
  return total;
}

// --- writers -----------------------------------------------------------------------------------
function csvCell(value, separator) {
  let text;
  if (value === null || value === undefined) text = "";
  else if (typeof value === "boolean") text = value ? "True" : "False";
  else if (isF(value) || typeof value === "number") text = pyNumber(value);
  else text = String(value);
  if (text.includes(separator) || text.includes('"') || text.includes("\r") || text.includes("\n")) {
    return '"' + text.replace(/"/g, '""') + '"';
  }
  return text;
}
function csvRow(cells, separator) {
  return cells.map(c => csvCell(c, separator)).join(separator) + "\r\n";
}
function writeCsv(columns, rows, trailer, cfg) {
  let out = "﻿";
  out += csvRow(headings(columns, headerStyle(cfg, "csv")), cfg.separator);
  for (const r of rows) {
    out += csvRow(columns.map(c => fmtNumber(guard(r[c] === undefined ? "" : r[c]), cfg)), cfg.separator);
  }
  out += "\r\n";
  out += csvRow(Object.keys(trailer).map(k => "# " + k + ": " + trailer[k]), cfg.separator);
  return out;
}
function jsonPayload(columns, rows, trailer, cfg, fmt) {
  const keys = headings(columns, headerStyle(cfg, fmt));
  return rows.map(r => {
    const obj = {};
    keys.forEach((k, i) => { obj[k] = r[columns[i]] === undefined ? "" : r[columns[i]]; });
    return obj;
  });
}
function writeJson(columns, rows, trailer, cfg) {
  return pyJson({ rows: jsonPayload(columns, rows, trailer, cfg, "json"), trailer: trailer }, 2, 0);
}
function writeJsonl(columns, rows, cfg) {
  return jsonPayload(columns, rows, {}, cfg, "jsonl").map(o => pyJson(o, 0, 0) + "\n").join("");
}

function escapeHtml(s) {
  return String(s === null || s === undefined ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#x27;");
}
function writeInventory(rows, trailer) {
  const key = r => {
    const asn = r.archive_serial_number;
    return [(asn === "" || asn === null || asn === undefined) ? 1 : 0,
            typeof asn === "number" ? asn : 0];
  };
  const ordered = rows.map((r, i) => [key(r), i, r])
    .sort((a, b) => a[0][0] - b[0][0] || a[0][1] - b[0][1] || a[1] - b[1])
    .map(x => x[2]);
  const has = r => !(r.archive_serial_number === "" || r.archive_serial_number === null ||
                     r.archive_serial_number === undefined);
  const withAsn = ordered.filter(has);
  const without = ordered.filter(r => !has(r));
  const table = items => items.map(r =>
    "<tr><td class='asn'>" + escapeHtml(r.archive_serial_number || "") +
    "</td><td>" + escapeHtml(r.title) + "</td><td>" + escapeHtml(r.correspondent) +
    "</td><td>" + escapeHtml(r.document_type) + "</td><td>" + escapeHtml(r.created) + "</td></tr>"
  ).join("\n");
  const head = "<table><thead><tr><th>ASN</th><th>Title</th><th>Correspondent</th><th>Type</th>" +
               "<th>Created</th></tr></thead>";
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Document inventory</title>
<style>
 body { font: 11pt/1.4 -apple-system, Segoe UI, Helvetica, Arial, sans-serif; color:#000; background:#fff; margin:24px; }
 h1 { font-size:16pt; margin:0 0 4px; } p.meta { color:#444; margin:0 0 16px; font-size:9pt; }
 table { border-collapse:collapse; width:100%; }
 th, td { border-bottom:1px solid #bbb; padding:4px 6px; text-align:left; vertical-align:top; }
 th { border-bottom:2px solid #000; font-size:9pt; text-transform:uppercase; letter-spacing:.04em; }
 td.asn { font-variant-numeric:tabular-nums; white-space:nowrap; }
 h2 { font-size:12pt; margin:24px 0 6px; }
 tr { page-break-inside:avoid; } thead { display:table-header-group; }
 @page { margin:15mm; }
</style></head><body>
<h1>Document inventory</h1>
<p class="meta">${escapeHtml(trailer["rows written"])} documents &middot; ${escapeHtml(trailer["generated"])}</p>
${head}
<tbody>
${table(withAsn)}
</tbody></table>
${without.length ? "<h2>No archive serial number</h2>" + head + "<tbody>" + table(without) + "</tbody></table>" : ""}
</body></html>`;
}

// --- the run -----------------------------------------------------------------------------------
async function fetchDocuments(api, params, cfg) {
  const q = Object.assign({}, params, { page_size: String(PAGE_SIZE) });
  if (!cfg.content) q.truncate_content = "true";
  let data = await api.get("/api/documents/", q);
  const count = data.count || 0;
  let docs = (data.results || []).slice();
  let next = data.next;
  while (next) {
    const page = await api.getNext(next);
    if ((page.count === undefined ? count : page.count) !== count) {
      throw ExportError("the document count changed mid-export (" + count + " -> " + page.count +
        "). Something is writing to the instance. Re-run when it is quiet.");
    }
    docs = docs.concat(page.results || []);
    next = page.next;
  }
  return [docs, count];
}

// The whole config object, top to bottom. Dropping a key silently is the same failure this tool
// refuses for an unknown saved-view rule_type — a filter the user typed that never reaches the
// fetch, in a sheet that still reconciles. Matches the server's own refusal
// (paperless_serve.py argv_from_config) key for key and message for message, so which engine ran
// cannot change whether a misplaced key is caught.
const CONFIG_KEYS = ["base_url", "view", "filters", "sums", "columns", "content", "locale",
                     "date", "headers", "list_sep", "basename", "formats", "inventory"];

function normaliseConfig(raw) {
  const unknown = Object.keys(raw).filter(k => !CONFIG_KEYS.includes(k));
  if (unknown.length) {
    throw UsageError("unknown setting(s): " + unknown.slice().sort().join(", "));
  }
  const cfg = {
    baseUrl: raw.base_url || "",
    view: raw.view || null,
    filters: raw.filters || {},
    sums: raw.sums || [],
    columns: typeof raw.columns === "string"
      ? raw.columns.split(",").map(c => c.trim()).filter(c => c.length)
      : (raw.columns || null),
    content: !!raw.content,
    separator: raw.locale === "comma" ? ";" : ",",
    decimal: raw.locale === "comma" ? "," : ".",
    dateSpec: raw.date || "iso",
    headers: raw.headers || null,
    listSep: raw.list_sep === undefined || raw.list_sep === null ? "; " : raw.list_sep,
    basename: raw.basename || "export",
    formats: (raw.formats && raw.formats.length) ? raw.formats : ["csv"],
    inventory: !!raw.inventory,
  };
  cfg.dateFmt = resolveDateFormat(cfg.dateSpec);
  const allowed = ["csv", "json", "jsonl"];
  for (const f of cfg.formats) {
    if (!allowed.includes(f)) {
      throw UsageError("format '" + f + "' is not one this page writes. It writes " +
        allowed.join(", ") + " and the inventory sheet; xlsx and the PDF pack are command-line " +
        "features (see the README).");
    }
  }
  if (cfg.listSep === (cfg.separator === ";" ? ";" : ",")) {
    throw UsageError("list separator '" + cfg.listSep + "' is the CSV separator this locale uses. " +
      "Quoting would make it legal CSV and half the readers would still split the cell.");
  }
  if (cfg.view && Object.keys(cfg.filters).some(k => cfg.filters[k] &&
      (!Array.isArray(cfg.filters[k]) || cfg.filters[k].length))) {
    throw UsageError("a saved view carries its own filters; do not combine it with filter fields");
  }
  return cfg;
}

async function runExport(api, rawConfig, clock) {
  const started = (clock && clock.now ? clock.now() : Date.now());
  const cfg = normaliseConfig(rawConfig);
  const notes = [];
  const lk = new Lookups({
    correspondents: await api.getAll("/api/correspondents/"),
    document_types: await api.getAll("/api/document_types/"),
    tags: await api.getAll("/api/tags/"),
    storage_paths: await api.getAll("/api/storage_paths/"),
    custom_fields: await api.getAll("/api/custom_fields/"),
  });

  let params, sort = null, viewColumns = null;
  if (cfg.view) {
    const views = await api.getAll("/api/saved_views/");
    let match = views.filter(v => String(v.id) === String(cfg.view));
    if (!match.length) match = views.filter(v => v.name === cfg.view);
    if (!match.length) match = views.filter(v => v.name.toLowerCase() === String(cfg.view).toLowerCase());
    if (!match.length) {
      const names = views.map(v => v.name).sort().join(", ") || "(none)";
      throw UsageError("no saved view '" + cfg.view + "'. Available: " + names);
    }
    if (match.length > 1) {
      throw UsageError("saved view '" + cfg.view + "' is ambiguous (ids " + match.map(v => v.id) + ")");
    }
    [params, sort, viewColumns] = paramsFromView(match[0], notes);
  } else {
    params = paramsFromFlags(cfg, lk);
  }
  if (sort) params.ordering = sort;

  const [docs, apiCount] = await fetchDocuments(api, params, cfg);
  const columns = resolveColumns(cfg, lk, viewColumns, notes);
  const rows = docs.map(d => buildRow(d, lk, cfg, notes));

  if (cfg.formats.some(f => headerStyle(cfg, f) === "readable") || cfg.inventory) {
    const clash = readableClashes(columns);
    if (clash.length) {
      notes.push("readable headings " + JSON.stringify(clash) +
                 " would collide; those columns keep their raw names");
    }
  }
  const strays = docs.filter(d => d.root_document !== null && d.root_document !== undefined)
                     .map(d => d.id);
  if (strays.length) {
    throw ExportError("documents " + JSON.stringify(strays) +
      " are versions, not roots; refusing to export them as rows");
  }
  if (rows.length !== apiCount) {
    throw ReconcileError("rows written " + rows.length + " != api count " + apiCount +
      ". The export is not trustworthy.");
  }

  const outRows = rows.slice();
  if (cfg.sums.length) outRows.push(totalsRow(rows, cfg, lk, columns));

  const trailer = {
    "rows written": rows.length,
    "api count": apiCount,
    "filter": pyUrlencode(params) || "(none)",
    "formats": cfg.formats.join(", "),
    "headers": "",
    "date format": cfg.dateSpec,
    "list separator": "'" + cfg.listSep + "'",
    "generated": (clock && clock.stamp) ? clock.stamp : localStamp(new Date()),
    "elapsed": (clock && clock.elapsed !== undefined ? clock.elapsed
      : (((clock && clock.now ? clock.now() : Date.now()) - started) / 1000).toFixed(1) + "s"),
  };
  const seen = [];
  for (const n of notes) if (!seen.includes(n)) seen.push(n);
  if (seen.length) trailer.notes = seen.join(" | ");

  const files = [];
  for (const fmt of cfg.formats) {
    const perFile = Object.assign({}, trailer, { headers: headerStyle(cfg, fmt) });
    if (fmt === "csv") {
      files.push({ name: cfg.basename + ".csv", type: "text/csv", text: writeCsv(columns, outRows, perFile, cfg) });
    } else if (fmt === "json") {
      files.push({ name: cfg.basename + ".json", type: "application/json", text: writeJson(columns, outRows, perFile, cfg) });
    } else if (fmt === "jsonl") {
      files.push({ name: cfg.basename + ".jsonl", type: "application/json", text: writeJsonl(columns, outRows, cfg) });
    }
  }
  if (cfg.inventory) {
    files.push({ name: cfg.basename + ".inventory.html", type: "text/html",
                 text: writeInventory(rows, trailer) });
  }
  return { ok: true, trailer: Object.assign({}, trailer, { headers: headerStyle(cfg, cfg.formats[0]) }),
           files: files, columns: columns };
}

function localStamp(d) {
  const p = n => String(n).padStart(2, "0");
  return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()) + "T" +
         p(d.getHours()) + ":" + p(d.getMinutes()) + ":" + p(d.getSeconds());
}

const ENGINE = { RULE_MAP, VIEW_FIELD_MAP, DEFAULT_COLUMNS, runExport, writeCsv, writeJson,
                 writeJsonl, writeInventory, readableHeader, headings, guard, fmtNumber,
                 parseMonetary, fmtDate, pyJson, pyUrlencode, F, Lookups, paramsFromView,
                 paramsFromFlags, resolveColumns, buildRow, totalsRow, normaliseConfig };
if (typeof module !== "undefined" && module.exports) module.exports = ENGINE;
// ---- ENGINE END ----
</script>

<script nonce="__CSP_NONCE__">
"use strict";
// The session token. Module-scoped, in memory only: never web storage, never a cookie, never the
// DOM, never a URL after the first paint.
let SESSION = null;
let MODE = "disk";
let BUSY = false;
// Which build this file is. write_disk_copy() flips it; the served page is always false, so
// neither transport can be reached from the other.
const DISK_BUILD = false;
let API = null;          // disk mode: the fetch-backed client for the user's own instance
let RESULT_URLS = [];    // object URLs handed out for downloads, revoked when the next run lands

// name, label, kind, group. kind: text | area (one value per line) | select | check
const FIELDS = [
  ["view", "Saved view (id or name) — wins over every filter below", "text", "filters"],
  ["query", "Full text search", "text", "filters"],
  ["title", "Title contains", "text", "filters"],
  ["correspondent", "Correspondents, one per line", "area", "filters"],
  ["document_type", "Document types, one per line", "area", "filters"],
  ["tags", "Tags, one per line", "area", "filters"],
  ["storage_path", "Storage paths, one per line", "area", "filters"],
  ["created_from", "Created from (YYYY-MM-DD)", "text", "filters"],
  ["created_to", "Created to (YYYY-MM-DD)", "text", "filters"],
  ["custom_field_query", "Custom field query (paperless JSON)", "text", "filters"],
  ["sums", "Total these numeric custom fields, one per line", "area", "style"],
  ["columns", "Columns, comma separated (blank: the default set)", "text", "style"],
  ["locale", "Separator and decimal", "select", "style", [["dot", "comma , and dot ."], ["comma", "semicolon ; and comma ,"]]],
  ["date", "Dates", "select", "style", [["iso", "ISO 2026-03-04"], ["us", "US 03/04/2026"], ["eu", "EU 04.03.2026"]]],
  ["headers", "Column headings", "select", "style", [["", "default per format"], ["readable", "readable"], ["raw", "raw"]]],
  ["list_sep", "Joins multi-value cells", "text", "style"],
  ["basename", "File name, no extension", "text", "output"],
  ["pack_version", "Which PDF to pack", "select", "output", [["latest", "latest"], ["original", "original"]]],
];
const FORMATS = ["csv", "json", "jsonl", "xlsx"];
const EXTRAS = [
  ["content", "include the full OCR text column"],
  ["pack", "download the matching PDFs beside the sheet"],
  ["inventory", "also write the print-ready binder sheet"],
];

function el(tag, text) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}
function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }

function say(text, bad) {
  const box = document.getElementById("notice");
  box.textContent = text;
  box.classList.toggle("bad", !!bad);
  box.classList.remove("hidden");
}

async function api(path, options) {
  const opts = options || {};
  const headers = { "X-Session-Token": SESSION };
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(path, { method: opts.method || "GET", headers: headers, body: opts.body });
  if (!response.ok && response.status !== 400 && response.status !== 500) {
    throw new Error("the local server refused that request (" + response.status + ")");
  }
  return response.json();
}

// --- front 2: the browser talks to paperless itself ------------------------------------------
// The token is here, in this variable, and nowhere else: no storage, no cookie, no URL, no DOM.
function isPrivateHost(host) {
  const h = String(host || "").toLowerCase().replace(/\.$/, "");
  if (!h) return false;
  if (h === "localhost" || h.endsWith(".localhost") || h.endsWith(".local") ||
      h.endsWith(".home.arpa")) return true;
  const v4 = h.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
  if (v4) {
    const [a, b] = [parseInt(v4[1], 10), parseInt(v4[2], 10)];
    return a === 127 || a === 10 || (a === 192 && b === 168) ||
           (a === 172 && b >= 16 && b <= 31) || (a === 169 && b === 254);
  }
  const bare = h.replace(/^\[|\]$/g, "");
  if (bare === "::1") return true;
  if (/^f[cd][0-9a-f]{2}:/.test(bare) || /^fe80:/.test(bare)) return true;
  if (/^[0-9a-f:]+$/.test(bare)) return false;      // some other literal address
  // A name. The page cannot resolve it, so it cannot prove a dotted name is private the way the
  // command line does; it asks instead of assuming in our favour.
  return h.indexOf(".") === -1;
}

function checkUrl(raw, insecureWord) {
  let url;
  try { url = new URL(raw); } catch (err) { throw new Error("that is not a URL: " + raw); }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error("the address must start with http:// or https://");
  }
  if (url.search || url.hash) {
    throw new Error("refusing an address carrying a query or fragment (tokens never ride in URLs)");
  }
  if (location.protocol === "https:" && url.protocol === "http:") {
    throw new Error("this page is served over https and your paperless is plain http. The " +
      "browser blocks that as mixed content before the request is made. Serve this page over " +
      "http, or put your paperless behind https.");
  }
  if (url.protocol === "http:" && !isPrivateHost(url.hostname)) {
    if (insecureWord !== "insecure") {
      const err = new Error("that is plain http to " + url.hostname + ", which is not an address " +
        "this page can see is private. The token would travel in the clear.");
      err.needsInsecure = true;
      throw err;
    }
  }
  return url.origin + url.pathname.replace(/\/+$/, "");
}

function makeApi(base, token) {
  const baseOrigin = new URL(base).origin;
  async function call(path, params) {
    const url = new URL(base + path);
    if (params) for (const key of Object.keys(params)) url.searchParams.set(key, params[key]);
    let response;
    try {
      response = await fetch(url.toString(), {
        method: "GET",
        // The token is in a header, and a redirect is a way to move a header somewhere else.
        redirect: "error",
        credentials: "omit",
        headers: { "Authorization": "Token " + token,
                   "Accept": "application/json; version=10" },
      });
    } catch (err) {
      throw new Error("could not reach " + baseOrigin + path + ". If the address is right, this " +
        "is almost always the CORS step: see the note above.");
    }
    if (response.status === 401 || response.status === 403) {
      throw new Error("paperless refused the token (" + response.status + ")");
    }
    if (!response.ok) throw new Error(path + " returned HTTP " + response.status);
    return response.json();
  }
  function samePath(next) {
    const there = new URL(next, base);
    if (there.origin !== baseOrigin) {
      throw new Error("the API's next-page link points at another origin (" + there.origin +
        "); refusing to follow it. Check PAPERLESS_URL on the server.");
    }
    return there.pathname + there.search;
  }
  return {
    base: base,
    get: (path, params) => call(path, params),
    getNext: (next) => call(samePath(next)),
    getAll: async (path) => {
      let data = await call(path, { page_size: 1000 });
      let out = (data.results || []).slice();
      while (data.next) {
        data = await call(samePath(data.next));
        out = out.concat(data.results || []);
      }
      return out;
    },
  };
}

async function runOnDisk(config) {
  if (!API) throw new Error("connect to your paperless first");
  return ENGINE.runExport(API, Object.assign({}, config, { base_url: API.base }));
}

function buildForm(session) {
  const groups = {
    filters: document.getElementById("g-filters"),
    style: document.getElementById("g-style"),
    output: document.getElementById("g-output"),
  };
  const defaults = session.defaults || {};
  for (const spec of FIELDS) {
    const [name, label, kind, group, choices] = spec;
    const wrap = el("div");
    const lab = el("label", label);
    lab.setAttribute("for", "f-" + name);
    wrap.appendChild(lab);
    let field;
    if (name === "view" && session.views && session.views.length) {
      // Disk mode knows the instance's views before the export runs, so it offers them by name.
      field = el("select");
      const blank = el("option", "(no saved view)");
      blank.value = "";
      field.appendChild(blank);
      for (const v of session.views) {
        const option = el("option", v.name);
        option.value = String(v.id);
        field.appendChild(option);
      }
    } else if (kind === "select") {
      field = el("select");
      for (const [value, text] of choices) {
        const option = el("option", text);
        option.value = value;
        field.appendChild(option);
      }
    } else if (kind === "area") {
      field = el("textarea");
      field.rows = 2;
    } else {
      field = el("input");
      field.type = "text";
    }
    field.id = "f-" + name;
    field.name = name;
    const value = defaults[name];
    if (Array.isArray(value)) field.value = value.join("\n");
    else if (value !== undefined && value !== null) field.value = String(value);
    wrap.appendChild(field);
    groups[group].appendChild(wrap);
  }

  const formatBox = document.getElementById("g-formats");
  formatBox.appendChild(el("span", "Formats:"));
  for (const format of FORMATS) {
    const lab = el("label");
    const box = el("input");
    box.type = "checkbox";
    box.name = "format";
    box.value = format;
    if ((defaults.formats || ["csv"]).indexOf(format) >= 0) box.checked = true;
    if (format === "xlsx" && !session.xlsx) {
      box.checked = false;
      box.disabled = true;
    }
    lab.appendChild(box);
    lab.appendChild(el("span", format === "xlsx" && !session.xlsx
      ? "xlsx (" + (session.xlsxNote || "needs openpyxl") + ")" : format));
    formatBox.appendChild(lab);
  }

  const extraBox = document.getElementById("g-extras");
  for (const [name, text] of EXTRAS) {
    const lab = el("label");
    const box = el("input");
    box.type = "checkbox";
    box.name = name;
    box.checked = !!defaults[name];
    if (name === "pack" && session.pack === false) {
      // A zip of every PDF would be assembled in this tab, in memory, with no way to stream it
      // to disk in every browser, so disk mode does not offer --pack.
      box.checked = false;
      box.disabled = true;
    }
    lab.appendChild(box);
    lab.appendChild(el("span", name === "pack" && session.pack === false
      ? "the PDFs beside the sheet: that one is paperless-export --pack, at the command line"
      : text));
    extraBox.appendChild(lab);
  }
}

function collect() {
  // The served front takes the CLI's own flat shape (paperless_serve.py argv_from_config), one
  // key per flag. The disk engine takes the nested config object (normaliseConfig) — same form,
  // two wire shapes, so this is where they part ways rather than inside the engine. pack_version
  // has no meaning on disk (disk mode does not pack); the field stays in FIELDS because the form
  // is shared with front 3, which does pack.
  const config = {};
  const filters = {};
  for (const spec of FIELDS) {
    const [name, , kind, group] = spec;
    const field = document.getElementById("f-" + name);
    const raw = field.value.trim();
    if (!raw) continue;
    let value;
    if (kind === "area") {
      const lines = raw.split("\n").map(function (line) { return line.trim(); })
                       .filter(function (line) { return line.length > 0; });
      if (!lines.length) continue;
      value = lines;
    } else {
      value = raw;
    }
    if (MODE === "disk" && name === "pack_version") continue;
    if (MODE === "disk" && group === "filters" && name !== "view") filters[name] = value;
    else config[name] = value;
  }
  if (MODE === "disk" && Object.keys(filters).length) config.filters = filters;
  const formats = [];
  const boxes = document.getElementsByName("format");
  for (const box of boxes) if (box.checked) formats.push(box.value);
  config.formats = formats;
  for (const [name] of EXTRAS) {
    const box = document.getElementsByName(name)[0];
    if (box.checked) config[name] = true;
  }
  return config;
}

function showResult(answer) {
  const out = document.getElementById("result");
  clear(out);
  if (!answer.ok) {
    const box = el("div", answer.error);
    box.className = "msg bad";
    out.appendChild(box);
    return;
  }
  const table = el("table");
  // Everything below came from paperless or from the engine: textContent, never markup.
  for (const key of Object.keys(answer.trailer)) {
    const row = el("tr");
    row.appendChild(el("th", key));
    row.appendChild(el("td", answer.trailer[key]));
    table.appendChild(row);
  }
  out.appendChild(el("h2", "Result"));
  out.appendChild(table);
  out.appendChild(el("p", "These links are the newest run's. Running again replaces them; the " +
    "earlier run's files stay on disk in their own folder."));
  const list = el("ul");
  list.className = "files";
  for (const url of RESULT_URLS) URL.revokeObjectURL(url);
  RESULT_URLS = [];
  for (const file of answer.files) {
    const item = el("li");
    const link = el("a", file.name);
    if (MODE === "served") {
      link.href = "/files/" + encodeURIComponent(file.name);
      item.appendChild(link);
      item.appendChild(el("span", "  " + file.bytes + " bytes"));
    } else {
      // Built here, in the tab. The click is the user's: nothing is saved because they pressed Run.
      const bytes = new TextEncoder().encode(file.text);
      const blob = new Blob([file.name.endsWith(".csv") ? bytes : file.text],
                            { type: file.type + ";charset=utf-8" });
      const href = URL.createObjectURL(blob);
      RESULT_URLS.push(href);
      link.href = href;
      item.appendChild(link);
      item.appendChild(el("span", "  " + bytes.length + " bytes"));
    }
    link.setAttribute("download", file.name);
    list.appendChild(item);
  }
  out.appendChild(list);
  out.appendChild(el("p", MODE === "served"
    ? "The same files are on disk in " + answer.run_dir
    : "Save each file where you want it. Nothing was written until you click."));
}

async function onSubmit(event) {
  event.preventDefault();
  if (BUSY) return;
  const config = collect();
  if (!config.formats.length) { say("Pick at least one format.", true); return; }
  BUSY = true;
  document.getElementById("run").disabled = true;
  document.getElementById("status").textContent = "running";
  try {
    const answer = MODE === "served"
      ? await api("/run", { method: "POST", body: JSON.stringify(config) })
      : await runOnDisk(config);
    showResult(answer);
    document.getElementById("status").textContent = answer.ok ? "done" : "failed";
  } catch (err) {
    say(err.message, true);
    document.getElementById("status").textContent = "failed";
  } finally {
    BUSY = false;
    document.getElementById("run").disabled = false;
  }
}

async function onQuit() {
  window.removeEventListener("beforeunload", warnOnLeave);
  try { await api("/quit", { method: "POST", body: "{}" }); } catch (err) { /* it died, which is the point */ }
  SESSION = null;
  document.getElementById("form").classList.add("hidden");
  say("Session closed. The files of any finished run are still on disk.");
}

function warnOnLeave(event) {
  if (!SESSION) return;
  event.preventDefault();
  event.returnValue = "";
}

const CORS_HELP =
  "Your paperless has to say this page may read it. On the machine running paperless, set\n" +
  "  PAPERLESS_CORS_ALLOWED_HOSTS=<the origin this page is served from>\n" +
  "and restart it. Serving this file from an origin you control is the safe way:\n" +
  "  python3 -m http.server 9001   ->   PAPERLESS_CORS_ALLOWED_HOSTS=http://localhost:9001\n" +
  "Opening it straight from the disk works too, with PAPERLESS_CORS_ALLOWED_HOSTS=null, but " +
  "read the warning below before you do.";

const NULL_WARNING =
  "You are running this page from a file, so its origin is 'null'. If you allowed null on your " +
  "paperless, take it back out when you are done: every sandboxed frame on the web has that same " +
  "origin, so while it is set, any page you visit can read your archive - and delete from it - " +
  "in a browser that is logged into paperless. Serving this file from an origin of your own " +
  "(python3 -m http.server 9001) does not have that problem.";

async function onConnect(event) {
  event.preventDefault();
  const status = document.getElementById("cstatus");
  const raw = document.getElementById("f-url").value.trim();
  const token = document.getElementById("f-token").value;
  if (!raw || !token) { say("Address and token, both.", true); return; }
  let base;
  try {
    base = checkUrl(raw, document.getElementById("f-insecure").value.trim().toLowerCase());
  } catch (err) {
    if (err.needsInsecure) document.getElementById("insecure-wrap").classList.remove("hidden");
    say(err.message, true);
    return;
  }
  status.textContent = "connecting";
  const api = makeApi(base, token);
  let fields;
  try {
    fields = await api.getAll("/api/custom_fields/");
  } catch (err) {
    status.textContent = "failed";
    say(err.message + "\n\n" + CORS_HELP, true);
    return;
  }
  API = api;
  status.textContent = "connected";
  document.getElementById("connect").classList.add("hidden");
  document.getElementById("sub").textContent =
    "front 2 - this page is talking to " + base + " itself. " + fields.length + " custom fields.";
  say(location.protocol === "file:" ? NULL_WARNING
      : "Connected. Your token is held in this tab only and is gone when you close it.",
      location.protocol === "file:");
  let views = [];
  try { views = await api.getAll("/api/saved_views/"); } catch (err) { views = []; }
  buildForm({ defaults: {}, xlsx: false, xlsxNote: "command line only",
              pack: false, views: views });
  document.getElementById("form").classList.remove("hidden");
  document.getElementById("form").addEventListener("submit", onSubmit);
}

function initDisk() {
  MODE = "disk";
  document.getElementById("sub").textContent = "opened from disk";
  document.getElementById("quit").classList.add("hidden");
  say(CORS_HELP);
  document.getElementById("connect").classList.remove("hidden");
  document.getElementById("connect").addEventListener("submit", onConnect);
}

async function init() {
  if (DISK_BUILD) return initDisk();
  const token = new URLSearchParams(location.search).get("s");
  if (location.protocol === "http:" && token) {
    SESSION = token;
    MODE = "served";
    // Off the address bar before anything else happens, so history keeps no copy.
    history.replaceState(null, "", "/");
  } else if (location.protocol === "http:") {
    document.getElementById("sub").textContent = "session over";
    say("This session has no token, which happens after a reload. Nothing is lost but the form: " +
        "the files of a finished run are already on disk. Press Ctrl-C in the terminal and run " +
        "paperless-export --serve again.");
    return;
  } else {
    // The served build reached over a scheme it does not serve on. Nothing to connect to.
    document.getElementById("sub").textContent = "wrong copy";
    say("This is the copy the command serves. For the file you open yourself, run: " +
        "python -m paperless_front front.html");
    return;
  }

  let session;
  try {
    session = await api("/session");
  } catch (err) {
    say(err.message, true);
    return;
  }
  document.getElementById("sub").textContent =
    "version " + session.version + "  ·  " + session.instance +
    "  ·  serving on 127.0.0.1 only, this session ends after " + session.idle + "s idle";
  buildForm(session);
  document.getElementById("form").classList.remove("hidden");
  document.getElementById("form").addEventListener("submit", onSubmit);
  document.getElementById("quit").addEventListener("click", onQuit);
  window.addEventListener("beforeunload", warnOnLeave);
}

init();
</script>
</body>
</html>
"""


def page(nonce: str) -> bytes:
    """The page with one response's CSP nonce in it."""
    if not nonce.replace("-", "").replace("_", "").isalnum():
        raise ValueError("nonce must be url-safe base64")
    return PAGE.replace(NONCE_MARK, nonce).encode("utf-8")


DISK_MARK = "const DISK_BUILD = false;"
DISK_FLIPPED = "const DISK_BUILD = true;"
VIEWPORT = '<meta name="viewport" content="width=device-width, initial-scale=1">'
# A file has no response headers, so the disk build states a policy in the document. It is weaker
# than front 3's by necessity — with no nonce, the page's own inline script needs 'unsafe-inline',
# which is most of what a CSP is for. What it still buys: no script, style, image, frame or font
# from anywhere else, and no form can post anywhere. The first line of defence is that nothing in
# this page ever becomes markup.
DISK_CSP = ('<meta http-equiv="Content-Security-Policy" content="'
            "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
            "connect-src *; img-src data:; form-action 'none'; base-uri 'none'"
            '">')


def disk_page() -> str:
    """Front 2's copy: no nonce (a file has no response headers) and the build constant flipped.

    Those two lines are the whole difference between the fronts, and test_front2.py says so.
    """
    if PAGE.count(DISK_MARK) != 1:
        raise ValueError("the build constant is not where it should be")
    return (PAGE.replace(' nonce="' + NONCE_MARK + '"', "")
                .replace(DISK_MARK, DISK_FLIPPED)
                .replace(VIEWPORT, VIEWPORT + "\n" + DISK_CSP, 1))


def write_disk_copy(path: str) -> None:
    """Bytes, not text: a text-mode write lets the platform's own newline translation in, and on
    Windows that turns every "\\n" into "\\r\\n" so the built file's md5 differs from the Mac's.
    The release asset is built once, on the Mac; it must be the same bytes if it were not.
    """
    with open(path, "wb") as handle:
        handle.write(disk_page().encode("utf-8"))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python -m paperless_front <path>   (writes the disk copy of the page)",
              file=sys.stderr)
        sys.exit(2)
    write_disk_copy(sys.argv[1])
    print(f"wrote {sys.argv[1]}")
