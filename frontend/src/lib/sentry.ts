/**
 * Error reporting, kept off the critical path.
 *
 * ``@sentry/vue`` is 31 kB gzipped and used to sit in the entry chunk,
 * where it was the single largest thing standing between an organiser
 * and the first paint. It only ever appeared in a production build,
 * because a local build has no ``VITE_SENTRY_DSN`` and Vite dropped the
 * whole ``init`` block as unreachable, which is why it went unnoticed.
 *
 * It is fetched after the app has mounted now. That leaves a window at
 * startup with nothing listening, which is the worst possible window to
 * lose: a crash while the app is booting is exactly the crash worth
 * hearing about. So this module goes in two steps.
 *
 * ``arm`` runs before mount and costs nothing. It installs plain
 * listeners that hold what they catch in memory. They are the window's
 * own, not a framework's: an error thrown while rendering reaches them
 * either way, and nothing here has to know what drew the page.
 *
 * ``start`` runs after mount, fetches Sentry, and replays everything the
 * buffer collected. From then on reports go straight through and the
 * temporary listeners are removed, so nothing is counted twice.
 */
type Report =
  | { kind: "message"; message: string; level: "warning" }
  | { kind: "error"; error: unknown };

// A boot loop could otherwise grow this without limit while offline. The
// first few reports are the ones that say what went wrong; the
// thousandth repeat of the same error says nothing new.
const MAX_BUFFERED = 50;

let sentry: typeof import("./sentry-client") | null = null;
let buffered: Report[] = [];

function hold(report: Report): void {
  if (buffered.length < MAX_BUFFERED) buffered.push(report);
}

/** Report a message. Used by the i18n missing-key tripwire. */
export function captureMessage(message: string, level: "warning"): void {
  if (sentry) sentry.captureMessage(message, level);
  else hold({ kind: "message", message, level });
}

/** Report a thrown value. */
export function captureError(error: unknown): void {
  if (sentry) sentry.captureException(error);
  else hold({ kind: "error", error });
}

function onWindowError(event: ErrorEvent): void {
  captureError(event.error ?? event.message);
}
function onRejection(event: PromiseRejectionEvent): void {
  captureError(event.reason);
}

/**
 * Start catching errors, before the app mounts. Synchronous and tiny:
 * two listeners and a Vue error handler that push onto an array.
 */
export function arm(): void {
  window.addEventListener("error", onWindowError);
  window.addEventListener("unhandledrejection", onRejection);
}

/**
 * Fetch Sentry and hand it everything caught so far.
 *
 * Called after ``mount``, so the download competes with nothing the
 * organiser is waiting for. Does nothing without a DSN, and nothing in
 * dev, which is the same rule as before: a local run should not need a
 * network round trip to report an error to somewhere it cannot reach.
 */
export async function start(): Promise<void> {
  const dsn = import.meta.env.VITE_SENTRY_DSN;
  if (!dsn || import.meta.env.DEV) return;

  // ``sentry-client`` rather than the package: see the note there. A
  // dynamic import of the whole namespace keeps every integration.
  const loaded = await import("./sentry-client");
  loaded.init({
    dsn,
    environment: import.meta.env.VITE_SENTRY_ENVIRONMENT || "production",
    // PII is off: no usernames, IPs or request bodies.
    sendDefaultPii: false,
    // Zero by default. Opkomst gets little traffic and tracing every
    // event would burn the free-tier quota fast. Bump it in env if you
    // want spans.
    tracesSampleRate: Number(import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE ?? 0),
  });

  // ``init`` installs Sentry's own global handlers, so ours would
  // double-report from here on.
  window.removeEventListener("error", onWindowError);
  window.removeEventListener("unhandledrejection", onRejection);

  sentry = loaded;
  const replay = buffered;
  buffered = [];
  for (const report of replay) {
    if (report.kind === "message") loaded.captureMessage(report.message, report.level);
    else loaded.captureException(report.error);
  }
}
