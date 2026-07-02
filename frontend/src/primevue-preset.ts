import { definePreset } from "@primeuix/themes";
import Aura from "@primeuix/themes/aura";

// Brand palette anchored at primary.500 (#9f000b) and a warm-cream
// surface scale that matches the app's hand-rolled --brand-bg /
// --brand-surface / --brand-border tokens. Because every PrimeVue
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
      // All three severities anchored on the brand palette so toasts
      // read as one coherent family on the cream background. Success
      // and error share the brand-red palette (Aura's defaults are
      // off-brand green and bright red); they're distinguished by the
      // built-in severity icons (check vs exclamation). Warn keeps a
      // warm amber/sand that harmonises with the cream surfaces
      // instead of Aura's screaming yellow.
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
            background: "color-mix(in srgb, #fff5e2, transparent 5%)",
            borderColor: "#ead9b3",
            color: "#7a5b00",
            detailColor: "{surface.700}",
            shadow: "0px 4px 8px 0px color-mix(in srgb, #b58a1a, transparent 96%)",
            closeButton: {
              hoverBackground: "#f6e4b8",
              focusRing: { color: "#7a5b00", shadow: "none" },
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
    primary: {
      50: "#fdf2f2",
      100: "#fbdadc",
      200: "#f5b0b4",
      300: "#ec7e85",
      400: "#dc4954",
      500: "#9f000b",
      600: "#8b000a",
      700: "#760008",
      800: "#5e0007",
      900: "#440005",
      950: "#2b0003",
    },
    colorScheme: {
      light: {
        // Surface scale — drives card / dialog / dropdown / input
        // backgrounds, borders, and muted text. 0 + 50 are the lightest
        // (card / dialog body), 200 is the warm border, 600 is muted
        // text, 900 is the body text. Kept warm-but-restrained so the
        // brand red stays the only saturated colour on screen.
        surface: {
          0: "#fbf7ee",
          50: "#f6f1e7",
          100: "#ece4d0",
          200: "#dcd2b9",
          300: "#c4b89b",
          400: "#a59882",
          500: "#7e7466",
          600: "#5e5a52",
          700: "#403d39",
          800: "#28261f",
          900: "#1a1a1a",
          950: "#0d0d0a",
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
