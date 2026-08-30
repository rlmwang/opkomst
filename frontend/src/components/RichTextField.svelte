<script lang="ts">
import { onMount } from "svelte";

import { t } from "@/i18n.svelte";
import {
  anchorAt,
  autolinkAll,
  autolinkAtCaret,
  isEditorEmpty,
  normalizeRichtext,
  textToRichtext,
} from "@/lib/richtext";

// A minimal rich-text editor for the "details" body. Its markup is
// deliberately constrained to exactly the marks the server sanitizer
// allows (bold / italic / underline / strikethrough / link, plus
// paragraphs and hard breaks), so what an organiser sees is exactly
// what gets stored — nothing the editor can produce is later stripped.
//
// No editor library: this is the browser's own ``contenteditable`` and
// ``document.execCommand``, which between them do all five marks. The
// two things the browser does not do are cleaning up the markup it
// produces (which differs per browser, and is a mess after a paste) and
// turning a typed URL into a link; both live in ``lib/richtext.ts``.
//
// ``fallbackHtml`` is the other language's formatted body: when this
// editor is empty it renders greyed behind the caret, so the organiser
// sees the real translation they're overwriting (the bilingual-edit
// fallback). It's a preview only, never emitted.
let {
  value = $bindable(),
  placeholder,
  fallbackHtml,
}: { value: string; placeholder?: string; fallbackHtml?: string | null } = $props();

let body = $state<HTMLElement>();
let empty = $state(true);
let active = $state({ bold: false, italic: false, underline: false, strike: false, link: false });
// What this field last wrote or last accepted, so the sync effect can
// tell the parent's value from its own echo.
let lastSeen = value;

function command(name: string, value?: string): void {
  try {
    document.execCommand(name, false, value);
  } catch {
    // execCommand is deprecated-but-universal; a browser that refuses
    // one command must not take the whole field down with it.
  }
}

function markActive(name: string): boolean {
  try {
    return document.queryCommandState(name);
  } catch {
    return false;
  }
}

/** Put the caret back in the field when the toolbar was used without it
 *  ever having been focused. Toolbar buttons suppress mousedown, so an
 *  existing selection survives and this is a no-op in the normal case. */
function focusEditable(): boolean {
  const el = body;
  if (!el) return false;
  const selection = document.getSelection();
  if (!selection || selection.rangeCount === 0 || !el.contains(selection.anchorNode)) el.focus();
  return true;
}

/** Recompute what the toolbar shows. Driven by ``selectionchange``
 *  rather than by input, because moving the caret through existing bold
 *  text has to light the button without anything being typed. */
function refresh(): void {
  const el = body;
  if (!el) return;
  empty = isEditorEmpty(el);
  const selection = document.getSelection();
  if (!selection || selection.rangeCount === 0 || !el.contains(selection.anchorNode)) return;
  active = {
    bold: markActive("bold"),
    italic: markActive("italic"),
    underline: markActive("underline"),
    strike: markActive("strikeThrough"),
    link: anchorAt(selection.anchorNode, el) !== null,
  };
}

function emitValue(): void {
  const el = body;
  if (!el) return;
  // Normalized on the way out, never in place: rewriting the live DOM
  // under the caret is how an editor eats a keystroke. The browser's own
  // markup renders identically, so there is nothing to see.
  value = normalizeRichtext(el.innerHTML);
  lastSeen = value;
}

function onInput(event: Event): void {
  // Autolink on the space that finished the URL, which is when TipTap
  // used to do it. Enter and paste are caught on blur instead.
  if ((event as InputEvent).data === " " && body) autolinkAtCaret(body);
  empty = body ? isEditorEmpty(body) : true;
  emitValue();
}

function onBlur(): void {
  const el = body;
  if (!el) return;
  autolinkAll(el);
  emitValue();
}

/** Paste is cleaned before it lands, not after. Word and Google Docs put
 *  hundreds of styled spans on the clipboard, and letting them into the
 *  DOM first means the organiser watches them get taken away again. */
function onPaste(event: ClipboardEvent): void {
  event.preventDefault();
  const data = event.clipboardData;
  if (!data) return;
  const html = data.getData("text/html");
  const text = data.getData("text/plain");
  const clean = html ? normalizeRichtext(html) : "";
  command("insertHTML", clean || textToRichtext(text));
  emitValue();
}

/** Links open on click in a contenteditable in some browsers, which
 *  loses the organiser's work. Editing is what a click means here. */
function onClick(event: MouseEvent): void {
  const el = body;
  if (el && anchorAt(event.target as Node, el)) event.preventDefault();
}

function toggle(mark: "bold" | "italic" | "underline" | "strike"): void {
  if (!focusEditable()) return;
  command({ bold: "bold", italic: "italic", underline: "underline", strike: "strikeThrough" }[mark]);
  refresh();
  emitValue();
}

function setLink(): void {
  const el = body;
  if (!el || !focusEditable()) return;
  const selection = document.getSelection();
  if (!selection || selection.rangeCount === 0) return;

  // Clicking anywhere inside a link edits the whole link, so the
  // organiser never has to select it by hand first.
  const existing = anchorAt(selection.anchorNode, el);
  if (existing) {
    const whole = document.createRange();
    whole.selectNodeContents(existing);
    selection.removeAllRanges();
    selection.addRange(whole);
  }
  // The prompt takes the selection away with it, so keep a copy.
  const saved = selection.getRangeAt(0).cloneRange();

  const url = window.prompt(t("richtext.linkPrompt"), existing?.getAttribute("href") ?? "https://");
  if (url === null) return; // cancelled

  selection.removeAllRanges();
  selection.addRange(saved);
  el.focus();

  if (url.trim() === "") command("unlink");
  else command("createLink", url.trim());
  refresh();
  emitValue();
}

onMount(() => {
  const el = body;
  if (!el) return;
  el.innerHTML = value || "";
  empty = isEditorEmpty(el);
  // Tags, not inline styles, and paragraphs, not divs: both are global
  // document flags, and both are what makes execCommand's output match
  // the tag set the server accepts.
  command("styleWithCSS", "false");
  command("defaultParagraphSeparator", "p");
  document.addEventListener("selectionchange", refresh);
  return () => document.removeEventListener("selectionchange", refresh);
});

// Sync when the parent replaces the value out from under us: an edit
// page that loads the existing entity after mount. Skipped while the
// field has focus, so the caret never jumps, and guarded on the value so
// the field's own writes do not come straight back at it.
$effect(() => {
  if (value === lastSeen) return;
  lastSeen = value;
  const el = body;
  if (!el || el === document.activeElement) return;
  if ((value || "") !== normalizeRichtext(el.innerHTML)) el.innerHTML = value || "";
  empty = isEditorEmpty(el);
});
</script>

<div class="rt">
  <div class="rt-toolbar">
    <button
      type="button"
      class="rt-btn"
      class:active={active.bold}
      title={t("richtext.bold")}
      aria-label={t("richtext.bold")}
      onmousedown={(e) => e.preventDefault()}
      onclick={() => toggle("bold")}
    >
      <strong>B</strong>
    </button>
    <button
      type="button"
      class="rt-btn"
      class:active={active.italic}
      title={t("richtext.italic")}
      aria-label={t("richtext.italic")}
      onmousedown={(e) => e.preventDefault()}
      onclick={() => toggle("italic")}
    >
      <em>I</em>
    </button>
    <button
      type="button"
      class="rt-btn"
      class:active={active.underline}
      title={t("richtext.underline")}
      aria-label={t("richtext.underline")}
      onmousedown={(e) => e.preventDefault()}
      onclick={() => toggle("underline")}
    >
      <span style="text-decoration: underline">U</span>
    </button>
    <button
      type="button"
      class="rt-btn"
      class:active={active.strike}
      title={t("richtext.strike")}
      aria-label={t("richtext.strike")}
      onmousedown={(e) => e.preventDefault()}
      onclick={() => toggle("strike")}
    >
      <span style="text-decoration: line-through">S</span>
    </button>
    <button
      type="button"
      class="rt-btn"
      class:active={active.link}
      title={t("richtext.link")}
      aria-label={t("richtext.link")}
      onmousedown={(e) => e.preventDefault()}
      onclick={setLink}
    >
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
        <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
      </svg>
    </button>
  </div>
  <div class="rt-body">
    <div class="rt-content">
      <!-- svelte-ignore a11y_no_static_element_interactions -->
      <!-- svelte-ignore a11y_click_events_have_key_events -->
      <div
        bind:this={body}
        class="rt-editable"
        contenteditable="true"
        role="textbox"
        aria-multiline="true"
        tabindex="0"
        data-placeholder={fallbackHtml ? "" : (placeholder ?? "")}
        data-empty={empty}
        oninput={onInput}
        onblur={onBlur}
        onpaste={onPaste}
        onclick={onClick}
      ></div>
    </div>
    <!-- Greyed fallback: the other language's body, shown only while
         this editor is empty. Non-interactive so clicks focus the editor
         beneath. -->
    {#if fallbackHtml && empty}
      <div class="rt-fallback richtext" aria-hidden="true">{@html fallbackHtml}</div>
    {/if}
  </div>
</div>

<style>
.rt {
  border: 1px solid var(--brand-border);
  border-radius: 8px;
  background: var(--brand-surface);
  overflow: hidden;
}
.rt-toolbar {
  display: flex;
  gap: 0.125rem;
  padding: 0.25rem;
  border-bottom: 1px solid var(--brand-border);
  background: color-mix(in srgb, var(--brand-surface) 92%, var(--brand-border));
}
.rt-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--brand-text);
  cursor: pointer;
  font-size: 0.95rem;
  line-height: 1;
}
.rt-btn:hover {
  background: color-mix(in srgb, var(--brand-border) 60%, transparent);
}
.rt-btn.active {
  background: var(--brand-red);
  color: #fff;
}
.rt-body {
  position: relative;
}
/* The other-language body, faded, overlaid on the empty editor. Same
 * padding as the editable content so the text lines up; pointer-events
 * off so it never steals focus from the editor beneath. */
.rt-fallback {
  position: absolute;
  inset: 0;
  padding: 0.625rem 0.75rem;
  color: var(--brand-text-muted);
  opacity: 0.55;
  line-height: 1.5;
  overflow: hidden;
  pointer-events: none;
}
.rt-fallback :global(p) {
  margin: 0 0 0.5rem;
}
.rt-editable {
  min-height: 5.5rem;
  padding: 0.625rem 0.75rem;
  outline: none;
  line-height: 1.5;
}
/* The content is written by the browser at runtime, so it never carries
 * the scope attribute: these have to be :global(). */
.rt-editable :global(p) {
  margin: 0 0 0.5rem;
}
.rt-editable :global(p:last-child) {
  margin-bottom: 0;
}
.rt-editable :global(a) {
  color: var(--brand-red);
  text-decoration: underline;
}
/* Placeholder on an empty field. Floated with no height so it sits on
 * the first line without taking space from it. */
.rt-editable[data-empty="true"]::before {
  content: attr(data-placeholder);
  float: left;
  height: 0;
  color: var(--brand-text-muted);
  pointer-events: none;
}
</style>
