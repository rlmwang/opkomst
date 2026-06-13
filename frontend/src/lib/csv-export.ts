/**
 * Client-side CSV download for organiser exports (event feedback,
 * form submissions). One escape rule, one BOM, one download dance —
 * shared so the two details pages can't drift.
 */

/** RFC 4180 field escaping: quote a value only if it contains a
 *  comma, double-quote, or newline; double any embedded quotes. */
function csvField(value: unknown): string {
  const s = String(value ?? "");
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

/** Serialise a grid of rows (header first) to a CSV string. */
export function toCsv(rows: unknown[][]): string {
  return rows.map((row) => row.map(csvField).join(",")).join("\n");
}

/** Trigger a browser download of ``rows`` as ``filename``. Prepends a
 *  UTF-8 BOM so Excel on Windows reads diacritics correctly rather
 *  than mojibaking Dutch text. */
export function downloadCsv(filename: string, rows: unknown[][]): void {
  const blob = new Blob(["﻿", toCsv(rows)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
