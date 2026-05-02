/**
 * File-system-safe slug for download filenames.
 *
 * Lowercase, ASCII-ish, dash-separated. Strips punctuation that
 * some operating systems refuse in filenames (Windows colon /
 * pipe / asterisk, macOS slash) and trims runs of dashes so the
 * result reads cleanly. Used for CSV exports where the filename
 * carries the event name.
 */
export function filenameSlug(value: string): string {
  return value
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);
}
