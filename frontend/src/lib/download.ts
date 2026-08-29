/**
 * Save a file the API serves.
 *
 * The organiser exports (a form's answers, a datepoll's dates, an
 * event's feedback) are written by the server and streamed
 * (``services/csv_export``), so the browser's job is to hand the bytes
 * to the downloads folder. A plain link cannot: every one of these
 * routes wants the session's bearer token, which only ``fetch`` can
 * carry. The filename comes from the response, so the server names the
 * file it wrote.
 */
import { getToken } from "@/api/client";

function filenameOf(disposition: string | null, fallback: string): string {
  const match = disposition?.match(/filename="([^"]+)"/);
  return match ? match[1] : fallback;
}

export async function downloadFile(path: string, fallbackName: string): Promise<void> {
  const token = getToken();
  const resp = await fetch(path, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!resp.ok) throw new Error(`${resp.status}`);
  const url = URL.createObjectURL(await resp.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filenameOf(resp.headers.get("content-disposition"), fallbackName);
  a.click();
  URL.revokeObjectURL(url);
}
