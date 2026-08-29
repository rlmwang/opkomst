import type { Directive } from "vue";

/**
 * ``v-tooltip.top``, the app's own. Was PrimeVue's directive, 22 kB for
 * a label that follows the cursor's element.
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
let tip: HTMLElement | null = null;

function node(): HTMLElement {
  if (tip) return tip;
  tip = document.createElement("div");
  tip.className = "app-tooltip";
  tip.setAttribute("aria-hidden", "true");
  document.body.appendChild(tip);
  return tip;
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
  if (tip) tip.style.display = "none";
}

export const tooltip: Directive<HTMLElement, string | undefined> = {
  mounted(el, binding) {
    const text = () => binding.value ?? "";
    const enter = () => {
      if (text()) show(el, text());
    };
    el.addEventListener("mouseenter", enter);
    el.addEventListener("focus", enter);
    el.addEventListener("mouseleave", hide);
    el.addEventListener("blur", hide);
    // Tapping a button should not leave its label stranded on screen.
    el.addEventListener("click", hide);
  },
  unmounted() {
    hide();
  },
};
