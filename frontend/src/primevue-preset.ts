import { definePreset } from "@primeuix/themes";
import Aura from "@primeuix/themes/aura";

// Brand palette anchored at primary.500 and a surface scale that
// matches the app's hand-rolled --brand-bg / --brand-surface /
// --brand-border tokens — both read from the tenant's tokens.css at
// runtime, so this preset names no colour. Because every PrimeVue
// component (Dialog, Select, AutoComplete, Card, DatePicker, etc.) reads
// from these same surface shades, the components end up exactly the same
// cream as the rest of the app — no separate CSS overrides needed.
//
// Lives in its own module (not the admin ``main.ts``) so the public
// mini-apps can pull the *same* preset when they need a PrimeVue control
// (e.g. the chore page's DatePicker) without re-declaring it and drifting.
export const OpkomstPreset = definePreset(Aura, {
  components: {
    toast: {
      // ONE toast colour: every severity sits on the brand-red palette
      // (Aura's defaults are off-brand green/yellow/red), distinguished
      // only by the built-in severity icons (check / triangle /
      // exclamation). Severity colour-coding isn't worth the visual
      // noise — toasts are rare enough that users read the text, not
      // the hue. The public mini-apps' PublicToast.vue mirrors these
      // exact values.
      colorScheme: {
        light: {
          success: {
            background: "color-mix(in srgb, {primary.50}, transparent 5%)",
            borderColor: "{primary.200}",
            color: "{primary.600}",
            detailColor: "{surface.700}",
            shadow: "0px 4px 8px 0px color-mix(in srgb, {primary.500}, transparent 96%)",
            closeButton: {
              hoverBackground: "{primary.100}",
              focusRing: { color: "{primary.600}", shadow: "none" },
            },
          },
          error: {
            background: "color-mix(in srgb, {primary.50}, transparent 5%)",
            borderColor: "{primary.200}",
            color: "{primary.600}",
            detailColor: "{surface.700}",
            shadow: "0px 4px 8px 0px color-mix(in srgb, {primary.500}, transparent 96%)",
            closeButton: {
              hoverBackground: "{primary.100}",
              focusRing: { color: "{primary.600}", shadow: "none" },
            },
          },
          warn: {
            background: "color-mix(in srgb, {primary.50}, transparent 5%)",
            borderColor: "{primary.200}",
            color: "{primary.600}",
            detailColor: "{surface.700}",
            shadow: "0px 4px 8px 0px color-mix(in srgb, {primary.500}, transparent 96%)",
            closeButton: {
              hoverBackground: "{primary.100}",
              focusRing: { color: "{primary.600}", shadow: "none" },
            },
          },
        },
      },
    },
    toggleswitch: {
      colorScheme: {
        light: {
          root: {
            background: "{surface.200}",
            hoverBackground: "{surface.300}",
            checkedBackground: "{primary.color}",
            checkedHoverBackground: "{primary.hover.color}",
            borderColor: "{surface.300}",
            hoverBorderColor: "{surface.400}",
            checkedBorderColor: "{primary.color}",
            checkedHoverBorderColor: "{primary.hover.color}",
          },
          handle: {
            background: "{surface.0}",
            hoverBackground: "{surface.0}",
            checkedBackground: "{surface.0}",
            checkedHoverBackground: "{surface.0}",
            color: "{text.muted.color}",
            hoverColor: "{text.color}",
            checkedColor: "{primary.color}",
            checkedHoverColor: "{primary.hover.color}",
          },
        },
      },
    },
  },
  semantic: {
    // Aura's default ``disabledOpacity: 0.6`` is too subtle on a
    // cream background — disabled icon-buttons read as "almost
    // active". Drop to 0.4 so the distinction is unambiguous on
    // the row's pencil/trash glyphs in particular.
    disabledOpacity: "0.4",
    // The ramps are the tenant's, read at runtime from the
    // ``brands/{tenant}/tokens.css`` the page linked before this bundle
    // loaded. PrimeVue emits these into its own ``--p-*`` variables, so
    // every widget is tinted by whichever brand the page is wearing —
    // one preset, no per-tenant build.
    primary: {
      50: "var(--brand-primary-50)",
      100: "var(--brand-primary-100)",
      200: "var(--brand-primary-200)",
      300: "var(--brand-primary-300)",
      400: "var(--brand-primary-400)",
      500: "var(--brand-primary-500)",
      600: "var(--brand-primary-600)",
      700: "var(--brand-primary-700)",
      800: "var(--brand-primary-800)",
      900: "var(--brand-primary-900)",
      950: "var(--brand-primary-950)",
    },
    colorScheme: {
      light: {
        // Surface scale — drives card / dialog / dropdown / input
        // backgrounds, borders, and muted text. 0 + 50 are the lightest
        // (card / dialog body), 200 is the warm border, 600 is muted
        // text, 900 is the body text. Kept warm-but-restrained so the
        // brand red stays the only saturated colour on screen.
        surface: {
          0: "var(--brand-surface-0)",
          50: "var(--brand-surface-50)",
          100: "var(--brand-surface-100)",
          200: "var(--brand-surface-200)",
          300: "var(--brand-surface-300)",
          400: "var(--brand-surface-400)",
          500: "var(--brand-surface-500)",
          600: "var(--brand-surface-600)",
          700: "var(--brand-surface-700)",
          800: "var(--brand-surface-800)",
          900: "var(--brand-surface-900)",
          950: "var(--brand-surface-950)",
        },
        formField: {
          // Form fields render on the card surface; bumping their
          // own background to surface.0 keeps them visually flush
          // with the card behind them.
          background: "{surface.0}",
          // Aura's default ``disabledBackground = {surface.200}``
          // is the warm-khaki tone our brand palette assigns at
          // that step — reads as olive/brown on a cream page. Use
          // ``{surface.50}`` instead: a barely-darker cream that
          // distinguishes disabled from enabled without
          // introducing a new colour into the surface family.
          disabledBackground: "{surface.50}",
          disabledColor: "{surface.500}",
          borderColor: "{surface.200}",
          color: "{surface.900}",
          placeholderColor: "{surface.500}",
        },
      },
    },
  },
});

// The options object passed to ``app.use(PrimeVue, …)`` — shared so the
// admin app and the public mini-apps configure PrimeVue identically.
export const primeVueConfig = {
  // Week starts on Monday across every PrimeVue date picker — matches
  // our own public MonthCalendar and Dutch convention. Deep-merged into
  // the default locale (mergeKeys), so day/month names are kept.
  locale: { firstDayOfWeek: 1 },
  theme: {
    preset: OpkomstPreset,
    options: {
      // Disable automatic dark mode — the app's own surface colors are
      // hard-coded light, so following the OS preference produces an
      // inconsistent half-dark / half-light render.
      darkModeSelector: ".app-dark-never-applied",
      cssLayer: { name: "primevue", order: "primevue, app" },
    },
  },
};
