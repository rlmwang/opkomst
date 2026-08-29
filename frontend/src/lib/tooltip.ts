import type { Directive } from "vue";

/**
 * ``v-tooltip.top``, the app's own, and the Svelte action beside it.
 * Was PrimeVue's directive, 22 kB for a label that follows the cursor's
 * element.
 *
 * One node, reused. It is appended to the body rather than positioned
 * inside the anchor, so no card that hides its overflow can clip it,
 * and it is aria-hidden because the trigger already carries the same
 * text as an ``aria-label`` at every call site.
 *
 * Only ``.top`` is supported, because that is the only modifier the app
 * uses. Aura's values: a 12.5rem cap, 0.5rem by 0.75rem of padding, and
 * a 0.25rem gutter between the label and what it describes.
 */
let tipNode: HTMLElement | null = null;

function node(): HTMLElement {
  if (tipNode) return tipNode;
  tipNode = document.createElement("div");
  tipNode.className = "app-tooltip";
  tipNode.setAttribute("aria-hidden", "true");
  document.body.appendChild(tipNode);
  return tipNode;
}

function show(anchor: HTMLElement, text: string): void {
  const el = node();
  el.textContent = text;
  el.style.visibility = "hidden";
  el.style.display = "block";
  const box = anchor.getBoundingClientRect();
  el.style.left = `${box.left + window.scrollX + box.width / 2 - el.offsetWidth / 2}px`;
  el.style.top = `${box.top + window.scrollY - el.offsetHeight - 4}px`;
  el.style.visibility = "visible";
}

function hide(): void {
  if (tipNode) tipNode.style.display = "none";
}

/** Bind one element to a label, and hand back the way to unbind it.
 *  Both the directive and the action are this plus their own wrapper. */
function bind(el: HTMLElement, text: () => string): () => void {
  const enter = () => {
    const label = text();
    if (label) show(el, label);
  };
  el.addEventListener("mouseenter", enter);
  el.addEventListener("focus", enter);
  el.addEventListener("mouseleave", hide);
  el.addEventListener("blur", hide);
  // Tapping a button should not leave its label stranded on screen.
  el.addEventListener("click", hide);
  return () => {
    el.removeEventListener("mouseenter", enter);
    el.removeEventListener("focus", enter);
    el.removeEventListener("mouseleave", hide);
    el.removeEventListener("blur", hide);
    el.removeEventListener("click", hide);
    hide();
  };
}

export const tooltip: Directive<HTMLElement, string | undefined> = {
  mounted(el, binding) {
    bind(el, () => binding.value ?? "");
  },
  unmounted() {
    hide();
  },
};

/** ``use:tip={"Kopieer link"}``, the same label from a Svelte
 *  component. */
export function tip(el: HTMLElement, label: string | undefined) {
  let current = label;
  const off = bind(el, () => current ?? "");
  return {
    update(next: string | undefined) {
      current = next;
    },
    destroy: off,
  };
}
