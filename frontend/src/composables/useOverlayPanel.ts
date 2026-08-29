import { onBeforeUnmount, onMounted, ref } from "vue";

/**
 * A panel that opens against a field and is teleported to the body.
 *
 * Extracted from ``DatePicker.vue``, which built it first and is now one
 * of five users: the date picker, the select, the multi-select, the
 * autocomplete and the popover all want the same four things and should
 * not each have their own version of them.
 *
 * * Positioned against the viewport rather than the anchor's parent,
 *   because a panel rendered inside a form is clipped by any card that
 *   hides its overflow. This is what PrimeVue's ``appendTo: "body"``
 *   was doing.
 * * Flipped above the field when there is no room below it.
 * * Closed by a pointer press anywhere else, caught in the capture
 *   phase so a button underneath does not act on the press that was
 *   only meant to dismiss.
 * * Closed by Escape, with focus handed back to whatever opened it.
 *
 * The anchor is usually a fixed element, so ``anchor`` is a ref the
 * caller binds. ``show`` also accepts one, for a popover that is opened
 * from a click and belongs to whichever button was pressed.
 *
 * ``matchAnchorWidth`` makes the panel at least as wide as the field it
 * hangs under, which is what a list wants and a popover does not.
 * ``gutter`` is the gap between the two, which only the popover asks
 * for. ``onEscape`` says where focus goes when Escape closes the panel;
 * without one it goes to the anchor, which is right whenever the anchor
 * is the thing the user was on.
 */
export function useOverlayPanel(
  options: { matchAnchorWidth?: boolean; gutter?: number; onEscape?: () => void } = {},
) {
  const { matchAnchorWidth = true, gutter = 0, onEscape } = options;
  const anchor = ref<HTMLElement>();
  const panel = ref<HTMLElement>();
  const open = ref(false);
  const style = ref<Record<string, string>>({});
  /** True while the panel sits above its anchor rather than below it. */
  const flipped = ref(false);

  function place(): void {
    const box = anchor.value;
    const el = panel.value;
    if (!box || !el) return;
    const rect = box.getBoundingClientRect();
    const height = el.offsetHeight;
    const width = el.offsetWidth;
    const below = window.innerHeight - rect.bottom;
    const flip = below < height + gutter + 8 && rect.top > height + gutter + 8;
    flipped.value = flip;
    // Kept inside the viewport: a menu hanging off a button near the
    // right edge would otherwise run past it.
    const left = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8));
    style.value = {
      position: "absolute",
      insetInlineStart: `${left + window.scrollX}px`,
      top: `${(flip ? rect.top - height - gutter : rect.bottom + gutter) + window.scrollY}px`,
      ...(matchAnchorWidth ? { minWidth: `${rect.width}px` } : {}),
    };
  }

  function show(target?: HTMLElement): void {
    if (open.value) return;
    if (target) anchor.value = target;
    open.value = true;
    // The panel has no size until it has rendered, and its height is
    // what decides whether it opens upward.
    requestAnimationFrame(place);
  }

  function hide(): void {
    open.value = false;
  }

  function toggle(target?: HTMLElement): void {
    if (open.value) hide();
    else show(target);
  }

  function onEscapeKey(event: KeyboardEvent): void {
    if (!open.value || event.key !== "Escape") return;
    event.preventDefault();
    hide();
    if (onEscape) onEscape();
    else anchor.value?.focus();
  }

  function onPointerDown(event: PointerEvent): void {
    if (!open.value) return;
    const target = event.target as Node;
    if (anchor.value?.contains(target) || panel.value?.contains(target)) return;
    hide();
  }

  onMounted(() => {
    document.addEventListener("pointerdown", onPointerDown, true);
    document.addEventListener("keydown", onEscapeKey, true);
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
  });
  onBeforeUnmount(() => {
    document.removeEventListener("pointerdown", onPointerDown, true);
    document.removeEventListener("keydown", onEscapeKey, true);
    window.removeEventListener("resize", place);
    window.removeEventListener("scroll", place, true);
  });

  return { anchor, panel, open, style, flipped, show, hide, toggle, place };
}
