/**
 * The submission behind a ``?s={token}`` link.
 *
 * The server resolves the token while it is already building the page
 * and writes the answer into the shell, next to the entity payload
 * (``backend/routers/spa.py``). Reading it here is what removes the
 * round-trip every "reopen my link" page used to pay after its bundle
 * had parsed, for something the server had in hand before it sent the
 * first byte.
 *
 * Three states, the same convention the entity payloads use:
 *
 * * an object  — the submission, use it
 * * ``null``   — the token opens nothing (unknown, or the thing behind
 *                it is archived); the same answer the API gives as a
 *                404 or a 410
 * * ``undefined`` — nobody filled the marker. Only the Vite dev server,
 *                which serves the shells unsubstituted, so the page
 *                fetches instead.
 *
 * Each mini-app carries its own ``ApiError``, so the ``null`` case is
 * raised by the caller rather than here.
 */

declare global {
  interface Window {
    __OPKOMST_SUBMISSION__?: unknown;
  }
}

export function inlinedSubmission<T>(): T | null | undefined {
  return window.__OPKOMST_SUBMISSION__ as T | null | undefined;
}
