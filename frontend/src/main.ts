import { mount } from "svelte";

import App from "./App.svelte";
import { initI18n } from "./i18n.svelte";
import { routes } from "./router/routes";
import { startRouter } from "./router/navigation.svelte";
import * as sentry from "@/lib/sentry";
import "./assets/theme.css";
import "./assets/forms.css";

// Start catching errors now, and fetch Sentry itself once the app is on
// screen (``lib/sentry.ts``). Arming is two listeners and an array; the
// 31 kB that does the reporting is not something an organiser should
// wait behind to see their dashboard.
sentry.arm();

// The active language is fetched, not bundled, so it has to be in hand
// before the first render or every string would paint as ``[key]``. It
// is one small request that starts alongside the entry chunk.
//
// The router starts before the mount, so the shell renders the page the
// visitor asked for rather than an empty column that fills in a tick
// later. Its own loading state covers the wait.
initI18n().then(async () => {
  const target = document.getElementById("app");
  if (!target) throw new Error("#app is missing");
  void startRouter(routes);
  mount(App, { target });
  // After mount on purpose: the download competes with nothing, and
  // anything that went wrong before this point is buffered and replayed
  // the moment it lands.
  void sentry.start();
});
