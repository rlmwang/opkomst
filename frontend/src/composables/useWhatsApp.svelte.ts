import { get, post } from "@/api/client";

/**
 * The WhatsApp blast tool's connection.
 *
 * Not a query. The data is one page's, it is gone when the page is, and
 * a cache would work against the contract that says forget when the
 * organiser leaves. Plain state and two timers.
 *
 * One ping does two jobs: the page posts a heartbeat every few seconds,
 * which both bumps the server's last-seen stamp, the thing the watchdog
 * tears the session down on, and answers with the current state. There
 * is no separate status poll.
 *
 * The QR is fetched whenever the state is anything but open. Evolution
 * rotates it about every 20 seconds, so the page refreshes faster than
 * that.
 */
export type WaState = "open" | "connecting" | "close" | "unknown" | "not_configured";

interface StatusBody {
  state: WaState;
}

interface QrBody {
  qr: string | null;
  pairingCode: string | null;
}

// Five seconds and not fifteen: the watchdog is per-worker in-memory
// state, and the load balancer spreads requests across workers, so each
// worker only sees one heartbeat every interval times the worker count.
// Ticking faster keeps every worker's stamp fresh enough never to trip
// on a healthy session. It costs the server nothing.
const HEARTBEAT_INTERVAL_MS = 5_000;
// Evolution rotates the QR about every 20 seconds, which mirrors
// WhatsApp's own pairing-token lifetime. Polling at the rotation
// cadence means often scanning a just-expired code and being told the
// device could not be linked.
const QR_REFRESH_INTERVAL_MS = 5_000;
// WhatsApp ends linked-device sessions from time to time and the client
// reconnects within seconds. Nobody should be yanked back to the QR on
// every blip, so the link counts as really gone only once a non-open
// state has held for this long.
const STATE_FLAP_GRACE_MS = 30_000;

export function whatsApp() {
  let state = $state<WaState>("unknown");
  /** When the server last confirmed the link was open. */
  let lastOpenAt = $state(0);
  let qr = $state<string | null>(null);
  let pairingCode = $state<string | null>(null);
  let lastError = $state<string | null>(null);

  let heartbeatTimer: number | null = null;
  let qrTimer: number | null = null;

  async function fetchStatus(): Promise<void> {
    try {
      const body = await post<StatusBody>("/api/v1/whatsapp/heartbeat", {});
      state = body.state;
      if (body.state === "open") lastOpenAt = Date.now();
      lastError = null;
    } catch (e) {
      state = "unknown";
      lastError = e instanceof Error ? e.message : String(e);
    }
  }

  async function fetchQr(): Promise<void> {
    try {
      const body = await get<QrBody>("/api/v1/whatsapp/qr");
      qr = body.qr;
      pairingCode = body.pairingCode;
    } catch (e) {
      lastError = e instanceof Error ? e.message : String(e);
    }
  }

  function onVisibilityChange(): void {
    // A background tab has its timers throttled to once a minute or
    // worse, which can lag the heartbeat past the watchdog's patience.
    // Firing on the way back bridges that.
    if (document.visibilityState === "visible") void fetchStatus();
  }

  function startPolling(): void {
    if (heartbeatTimer !== null) return;
    void fetchStatus();
    void fetchQr();
    heartbeatTimer = window.setInterval(() => void fetchStatus(), HEARTBEAT_INTERVAL_MS);
    // Refreshing the QR only matters while there is no link yet.
    qrTimer = window.setInterval(() => {
      if (state !== "open" && state !== "not_configured") void fetchQr();
    }, QR_REFRESH_INTERVAL_MS);
    document.addEventListener("visibilitychange", onVisibilityChange);
  }

  function stopPolling(): void {
    document.removeEventListener("visibilitychange", onVisibilityChange);
    if (heartbeatTimer !== null) {
      window.clearInterval(heartbeatTimer);
      heartbeatTimer = null;
    }
    if (qrTimer !== null) {
      window.clearInterval(qrTimer);
      qrTimer = null;
    }
  }

  async function disconnect(): Promise<void> {
    // Tear the session down and reset what is on screen. Polling keeps
    // running: somebody may want to link again without reloading, and
    // polling is what fetches the next QR.
    try {
      await post("/api/v1/whatsapp/logout", {});
    } catch {
      // Best effort. The watchdog is the safety net.
    }
    state = "close";
    lastOpenAt = 0;
    qr = null;
    pairingCode = null;
  }

  // Leaving the page stops the timers and ends the session. The page's
  // own ``pagehide`` covers a closed tab, which this cannot.
  $effect(() => () => {
    stopPolling();
    void disconnect();
  });

  return {
    /** The raw signal. */
    get state(): WaState {
      return state;
    },
    /**
     * What the page should react to.
     *
     * It differs from ``state`` only during a reconnect, where the raw
     * signal says closed for a few seconds. Keeping this at open means
     * the composer does not vanish from under somebody mid-message.
     */
    get stableState(): WaState {
      if (state === "open") return "open";
      if (lastOpenAt > 0 && Date.now() - lastOpenAt < STATE_FLAP_GRACE_MS) return "open";
      return state;
    },
    get reconnecting(): boolean {
      return state !== "open" && this.stableState === "open";
    },
    get qr(): string | null {
      return qr;
    },
    get pairingCode(): string | null {
      return pairingCode;
    },
    get lastError(): string | null {
      return lastError;
    },
    startPolling,
    stopPolling,
    fetchQr,
    disconnect,

    async send(number: string, text: string): Promise<{ ok: boolean; error?: string }> {
      try {
        await post("/api/v1/whatsapp/send", { number, text });
        return { ok: true };
      } catch (e) {
        return { ok: false, error: e instanceof Error ? e.message : String(e) };
      }
    },
  };
}
