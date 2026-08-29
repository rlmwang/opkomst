<script lang="ts">
/**
 * The app's button. Replaces PrimeVue's, across 78 call sites.
 *
 * Geometry is Aura's, from
 * ``@primeuix/themes/dist/aura/button/index.mjs``. The colours are not
 * all Aura's: ``theme.css`` already overrode the secondary button to the
 * soft-pink brand family, for both the solid and the text variant, and
 * those rules move in here where they belong. The public mini-apps'
 * ``.btn-secondary`` in ``theme.css`` is the same look as a plain class,
 * because those apps have no components from here.
 *
 * Only the variants the app actually asks for: primary, secondary and
 * danger, each solid or text, at default or small size. Aura also has
 * rounded, outlined, raised, link and four more severities. Nothing
 * used them, so they are not here.
 *
 * Two deliberate departures from Aura. Transitions run at 120ms, which
 * is what every control the app wrote itself already uses, rather than
 * Aura's 200ms. And danger is the brand red: Aura's is a red of its
 * own that no brand defines, so replicating it would have meant a
 * literal colour, which is not allowed outside ``brands/``.
 */
import type { Snippet } from "svelte";

import AppIcon, { type IconName } from "./AppIcon.svelte";

const {
  label,
  icon,
  severity,
  text,
  size,
  disabled,
  loading,
  type = "button",
  onclick,
  children,
}: {
  label?: string;
  /** An ``AppIcon`` name, e.g. ``plus``. */
  icon?: IconName;
  severity?: "secondary" | "danger";
  /** Transparent until hovered, for low-emphasis actions. */
  text?: boolean;
  size?: "small";
  disabled?: boolean;
  /** Swaps the icon for a spinner and stops the button responding. */
  loading?: boolean;
  type?: "button" | "submit" | "reset";
  onclick?: (event: MouseEvent) => void;
  children?: Snippet;
} = $props();
</script>

<button
  {type}
  class="app-btn {severity ? `app-btn-${severity}` : 'app-btn-primary'}"
  class:app-btn-text={text}
  class:app-btn-sm={size === "small"}
  class:app-btn-icon-only={!label && !children}
  disabled={disabled || loading}
  {onclick}
>
  {#if loading}
    <svg
      class="app-btn-spin"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      stroke-linecap="round"
      aria-hidden="true"
    >
      <path d="M21 12a9 9 0 1 1-6.22-8.56" />
    </svg>
  {:else if icon}
    <AppIcon name={icon} />
  {/if}
  {#if label}<span class="app-btn-label">{label}</span>{/if}
  {#if children}{@render children()}{/if}
</button>

<style>
.app-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  position: relative;
  overflow: hidden;
  cursor: pointer;
  user-select: none;
  font-family: inherit;
  font-feature-settings: inherit;
  font-size: 1rem;
  padding: 0.5rem 0.75rem;
  border: 1px solid transparent;
  border-radius: 6px;
  transition:
    background 120ms,
    color 120ms,
    border-color 120ms,
    outline-color 120ms;
  outline-color: transparent;
}
.app-btn-label {
  font-weight: 500;
}
.app-btn:focus-visible {
  outline: 1px solid var(--brand-primary-500);
  outline-offset: 2px;
}
/* Aura's disabledOpacity, which the preset lowered from 0.6 so a
 * disabled icon button on cream is unambiguous. */
.app-btn:disabled {
  opacity: 0.4;
  cursor: default;
}

.app-btn-sm {
  font-size: 0.875rem;
  padding: 0.375rem 0.625rem;
}
/* An icon with no label is a square, so a row of them lines up. */
.app-btn-icon-only {
  width: 2.5rem;
  padding-inline: 0;
  gap: 0;
}
.app-btn-sm.app-btn-icon-only {
  width: 2rem;
}

/* Primary: the brand accent, filled. */
.app-btn-primary {
  background: var(--brand-primary-500);
  border-color: var(--brand-primary-500);
  color: #fff;
}
.app-btn-primary:not(:disabled):hover {
  background: var(--brand-primary-600);
  border-color: var(--brand-primary-600);
}
.app-btn-primary:not(:disabled):active {
  background: var(--brand-primary-700);
  border-color: var(--brand-primary-700);
}

/* Secondary: the brand red at low saturation. Soft-pink fill, red text.
 * Stands out against the cream surfaces without competing with a
 * primary button. */
.app-btn-secondary {
  background: var(--brand-red-soft);
  border-color: var(--brand-red-soft-border);
  color: var(--brand-red);
}
.app-btn-secondary:not(:disabled):hover {
  background: var(--brand-red-soft-hover);
  border-color: var(--brand-red);
  color: var(--brand-red-strong);
}
.app-btn-secondary:not(:disabled):active {
  background: var(--brand-red-soft-active);
  border-color: var(--brand-red);
  color: var(--brand-primary-900);
}

.app-btn-danger {
  background: var(--brand-red);
  border-color: var(--brand-red);
  color: #fff;
}
.app-btn-danger:not(:disabled):hover {
  background: var(--brand-red-hover);
  border-color: var(--brand-red-hover);
}

/* The text variant of each: no fill until hovered. */
.app-btn-text {
  background: transparent;
  border-color: transparent;
}
.app-btn-text.app-btn-primary {
  color: var(--brand-primary-500);
}
.app-btn-text.app-btn-primary:not(:disabled):hover {
  background: var(--brand-primary-50);
  border-color: transparent;
  color: var(--brand-primary-600);
}
.app-btn-text.app-btn-secondary {
  color: var(--brand-red);
}
.app-btn-text.app-btn-secondary:not(:disabled):hover {
  background: var(--brand-red-soft);
  border-color: transparent;
  color: var(--brand-red-strong);
}
.app-btn-text.app-btn-secondary:not(:disabled):active {
  background: var(--brand-red-soft-hover);
  border-color: transparent;
  color: var(--brand-primary-900);
}
.app-btn-text.app-btn-danger {
  color: var(--brand-red);
}
.app-btn-text.app-btn-danger:not(:disabled):hover {
  background: var(--brand-red-soft);
  border-color: transparent;
  color: var(--brand-red-strong);
}

.app-btn-spin {
  animation: app-btn-spin 1s linear infinite;
  flex: 0 0 auto;
}
@keyframes app-btn-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
