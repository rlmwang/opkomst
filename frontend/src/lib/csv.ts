/**
 * Minimal CSV/TSV parser for the WhatsApp blast tool's recipient
 * list.
 *
 * Scope: the tool accepts hand-pasted or hand-exported CSV/TSV up
 * to a few hundred rows. The field separator is auto-detected per
 * paste: a tab in the header row picks TSV (matches a Google
 * Docs / Google Sheets cell-range paste verbatim), otherwise we
 * fall back to comma. RFC 4180 quoting is supported so
 * spreadsheets that emit ``"Doe, John"`` round-trip cleanly.
 * Newlines inside quoted fields are supported. No streaming, no
 * async; the whole blob is parsed in one pass.
 *
 * The first non-empty line is the header row. Header names are
 * lowercased and trimmed so ``Number`` and ``number`` collapse to
 * the same key. The caller picks which column holds the phone
 * number (default ``number``); the chosen column must exist in
 * the header row.
 *
 * Any other columns are passed through verbatim as merge tags:
 * a column named ``color`` is substitutable as ``{color}`` in the
 * composer.
 */

export interface ParsedRow {
  /** Original 1-based line number in the source text, for error messages. */
  line: number;
  /** Column values keyed by lowercased header name. Always includes ``number``. */
  fields: Record<string, string>;
  /** Normalised phone (digits only). Empty if the ``number`` cell was empty. */
  phone: string;
  /** Validation outcome. ``ok`` rows are eligible to send. */
  status: "ok" | "invalid";
  /** Human-readable failure reason when ``status === "invalid"``. */
  error?: string;
}

export interface ParseResult {
  /** The headers in source order, lowercased. */
  headers: string[];
  /** Every data row, valid and invalid. */
  rows: ParsedRow[];
  /** Top-level errors that prevent the file being usable at all. */
  fatal: string[];
}

// 11 digits minimum: NL mobile is 31 6 12345678 = 11 digits,
// which is the load-bearing case for this app. Anything shorter
// is almost certainly a typo (post-prefix noise like
// "31612345" was previously sneaking through and being
// reported as valid). 15 is the E.164 maximum.
const PHONE_DIGITS_RE = /^\d{11,15}$/;

/** Pick the field separator from the first non-empty line: prefer
 * tab if one appears (Google Docs / Google Sheets cell-range paste
 * is pure TSV), otherwise fall back to comma. The check is naive
 * (it doesn't honour quoting), which is fine in practice: a header
 * row with a literal tab inside a quoted cell is implausible. */
function detectDelimiter(text: string): "," | "\t" {
  const newline = text.search(/[\r\n]/);
  const firstLine = newline === -1 ? text : text.slice(0, newline);
  return firstLine.includes("\t") ? "\t" : ",";
}

function tokenize(text: string, delimiter: string): string[][] {
  const out: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let i = 0;
  let inQuotes = false;
  while (i < text.length) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"') {
        if (text[i + 1] === '"') {
          cell += '"';
          i += 2;
          continue;
        }
        inQuotes = false;
        i++;
        continue;
      }
      cell += c;
      i++;
      continue;
    }
    if (c === '"') {
      inQuotes = true;
      i++;
      continue;
    }
    if (c === delimiter) {
      row.push(cell);
      cell = "";
      i++;
      continue;
    }
    if (c === "\n" || c === "\r") {
      row.push(cell);
      cell = "";
      out.push(row);
      row = [];
      // Eat the LF half of a CRLF.
      if (c === "\r" && text[i + 1] === "\n") i++;
      i++;
      continue;
    }
    cell += c;
    i++;
  }
  // Flush trailing cell/row.
  row.push(cell);
  if (row.length > 1 || row[0] !== "") out.push(row);
  return out;
}

/** Normalise a phone cell to digits only, in the shape Evolution
 * expects (country code + subscriber, no plus, no separators).
 *
 * Cleansing rules, in order:
 *
 *   1. Strip whitespace and the common pretty-printing characters
 *      ``+ - ( ) .``.
 *   2. ``00`` international-dialing prefix is dropped.
 *   3. If a default ``countryCode`` was supplied:
 *      - leading ``0`` (national prefix) is replaced with the code,
 *      - numbers that don't already start with the code get it
 *        prepended (assumes the cell holds bare national digits).
 *      Numbers that already start with the code are left alone so
 *      we don't double-prefix.
 *   4. Without a country code, just the stripped digits are
 *      returned and validation will reject anything that doesn't
 *      already include a country code (8 digits is below the
 *      typical national-with-CC minimum).
 */
export function normalisePhone(raw: string, countryCode = ""): string {
  let n = raw.replace(/[\s\-().+]/g, "");
  if (n.startsWith("00")) n = n.slice(2);
  const cc = countryCode.replace(/\D/g, "");
  if (cc && n) {
    if (n.startsWith("0")) {
      n = cc + n.slice(1);
    } else if (!n.startsWith(cc)) {
      n = cc + n;
    }
  }
  return n;
}

export function parseCsv(text: string, phoneColumn = "number", countryCode = ""): ParseResult {
  const result: ParseResult = { headers: [], rows: [], fatal: [] };
  const trimmed = text.replace(/^﻿/, "");
  if (!trimmed.trim()) {
    result.fatal.push("emptyInput");
    return result;
  }

  const tokens = tokenize(trimmed, detectDelimiter(trimmed));
  if (tokens.length === 0) {
    result.fatal.push("emptyInput");
    return result;
  }

  const phoneKey = phoneColumn.trim().toLowerCase();
  const headerRow = tokens[0].map((h) => h.trim().toLowerCase());
  if (!headerRow.includes(phoneKey)) {
    result.fatal.push("missingPhoneColumn");
    return result;
  }
  result.headers = headerRow;

  const seenNumbers = new Set<string>();
  for (let i = 1; i < tokens.length; i++) {
    const cells = tokens[i];
    // Skip wholly empty lines so trailing newlines don't generate
    // phantom rows in the preview table.
    if (cells.length === 1 && cells[0].trim() === "") continue;

    const fields: Record<string, string> = {};
    for (let c = 0; c < headerRow.length; c++) {
      fields[headerRow[c]] = (cells[c] ?? "").trim();
    }
    const phone = normalisePhone(fields[phoneKey] ?? "", countryCode);
    let status: "ok" | "invalid" = "ok";
    let error: string | undefined;
    if (!phone) {
      status = "invalid";
      error = "emptyNumber";
    } else if (!PHONE_DIGITS_RE.test(phone)) {
      status = "invalid";
      error = "invalidNumber";
    } else if (seenNumbers.has(phone)) {
      status = "invalid";
      error = "duplicateNumber";
    } else {
      seenNumbers.add(phone);
    }
    result.rows.push({ line: i + 1, fields, phone, status, error });
  }
  return result;
}

/** Header columns the composer can use as merge tags. The phone column
 * is excluded since substituting your recipient's own phone number into
 * the message body is never the intent. */
export function mergeTags(headers: string[], phoneColumn = "number"): string[] {
  const key = phoneColumn.trim().toLowerCase();
  return headers.filter((h) => h !== key);
}

/** Substitute ``{tag}`` placeholders with row field values. Tags whose
 * column doesn't exist are left as-is; that lets the live preview show
 * the user that they typoed a column name. */
export function applyMerge(template: string, fields: Record<string, string>): string {
  return template.replace(/\{([a-z0-9_]+)\}/gi, (match, key: string) => {
    const lower = key.toLowerCase();
    return Object.prototype.hasOwnProperty.call(fields, lower) ? fields[lower] : match;
  });
}
