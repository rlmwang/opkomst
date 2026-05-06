/**
 * State for the WhatsApp blast tool.
 *
 * Not Vue Query. the data is ephemeral, single-page, and a
 * server cache would actively work against the "forget when the
 * user leaves" contract. Plain refs + a polling timer.
 *
 * One ping covers two jobs: the page POSTs ``/heartbeat`` every
 * 15s, which both bumps the server-side last-seen timestamp
 * (driving the watchdog tear-down) and returns the current
 * connection state. No need for a separate ``/status`` poll.
 *
 * The QR is fetched on demand whenever the state is anything
 * other than ``open``. Evolution rotates the QR every ~20s, so
 * the page refreshes it on the same cadence.
 */
import { onBeforeUnmount, ref } from "vue";
import { get, post } from "@/api/client";

export type WaState =
  | "open"
  | "connecting"
  | "close"
  | "unknown"
  | "not_configured";

interface StatusBody {
  state: WaState;
}

interface QrBody {
  qr: string | null;
  pairingCode: string | null;
}

// 5s, not 15s: the backend watchdog is per-uvicorn-worker
// in-memory state and the load balancer round-robins across N
// workers, so each worker only sees one heartbeat every
// ``HEARTBEAT_INTERVAL_MS * N``. Faster ticks here keep every
// worker's ``_last_seen`` fresh enough that the watchdog never
// trips a healthy session. Cheap on the server (no DB, no
// external HTTP if the watchdog is fresh).
const HEARTBEAT_INTERVAL_MS = 5_000;
// Evolution rotates the QR roughly every 20s, mirroring WhatsApp's
// own pairing-token lifetime. Poll well below that so the image
// on screen is never more than ~5s behind the live token; if we
// poll at the rotation cadence the user often ends up scanning a
// just-expired QR and gets WhatsApp's "Couldn't link device".
const QR_REFRESH_INTERVAL_MS = 5_000;

export function useWhatsApp() {
  const state = ref<WaState>("unknown");
  const qr = ref<string | null>(null);
  const pairingCode = ref<string | null>(null);
  const lastError = ref<string | null>(null);

  let heartbeatTimer: number | null = null;
  let qrTimer: number | null = null;

  async function fetchStatus(): Promise<void> {
    try {
      const body = await post<StatusBody>("/api/v1/whatsapp/heartbeat", {});
      state.value = body.state;
      lastError.value = null;
    } catch (e) {
      state.value = "unknown";
      lastError.value = e instanceof Error ? e.message : String(e);
    }
  }

  async function fetchQr(): Promise<void> {
    try {
      const body = await get<QrBody>("/api/v1/whatsapp/qr");
      qr.value = body.qr;
      pairingCode.value = body.pairingCode;
    } catch (e) {
      lastError.value = e instanceof Error ? e.message : String(e);
    }
  }

  function startPolling(): void {
    if (heartbeatTimer !== null) return;
    void fetchStatus();
    void fetchQr();
    heartbeatTimer = window.setInterval(() => void fetchStatus(), HEARTBEAT_INTERVAL_MS);
    // The QR auto-refresh only matters while we're not yet linked.
    qrTimer = window.setInterval(() => {
      if (state.value !== "open" && state.value !== "not_configured") {
        void fetchQr();
      }
    }, QR_REFRESH_INTERVAL_MS);
  }

  function stopPolling(): void {
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
    // Tear down the Evolution session and reset visible state.
    // Don't stop polling: the user may want to re-link without
    // refreshing the page, and polling is what fetches the next
    // QR. The component's ``onBeforeUnmount`` handles timer
    // cleanup when the page actually goes away.
    try {
      await post("/api/v1/whatsapp/logout", {});
    } catch {
      // Best-effort. The watchdog is the safety net.
    }
    state.value = "close";
    qr.value = null;
    pairingCode.value = null;
  }

  async function send(number: string, text: string): Promise<{ ok: boolean; error?: string }> {
    try {
      await post("/api/v1/whatsapp/send", { number, text });
      return { ok: true };
    } catch (e) {
      return { ok: false, error: e instanceof Error ? e.message : String(e) };
    }
  }

  onBeforeUnmount(() => {
    stopPolling();
    // Best-effort ``pagehide`` already runs in the page itself for
    // the tab-close case; calling logout here covers normal SPA
    // navigation away from the page.
    void disconnect();
  });

  return {
    state,
    qr,
    pairingCode,
    lastError,
    startPolling,
    stopPolling,
    fetchQr,
    disconnect,
    send,
  };
}
