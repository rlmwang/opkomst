/** The rich-text body, without an editor library.
 *
 * ``RichTextField.svelte`` is a plain ``contenteditable`` driven by
 * ``document.execCommand``. The browser does the editing; this module
 * does the two jobs the browser does badly.
 *
 * **Cleanup.** Browsers disagree about the markup they produce for the
 * same keystroke: ``<b>`` or ``<strong>``, ``<strike>`` or ``<s>``,
 * ``<div>`` or ``<p>`` for a new line. Paste is worse, because the
 * clipboard carries whatever Word or Google Docs felt like writing.
 * ``normalizeRichtext`` rewrites any of it into the closed tag set
 * ``backend/services/sanitize.py`` accepts: paragraphs, line breaks,
 * five inline marks, and links whose scheme is http, https or mailto.
 * The server enforces the same list, so this is not the security
 * boundary; it is what keeps the stored body stable across browsers.
 *
 * **Autolink.** Typing a URL and pressing space should turn it into a
 * link, which no browser does on its own.
 *
 * Both are pure DOM work, kept out of the component so they can be
 * tested without mounting anything.
 */

/** Forced on every link. The server sets it too; matching here means the
 *  markup does not change shape on the first save. */
export const LINK_REL = "nofollow noopener noreferrer";

// Tag -> the mark it becomes. Covers what execCommand emits across
// browsers and what a paste is likely to carry.
const MARKS: Record<string, string> = {
  B: "strong",
  STRONG: "strong",
  I: "em",
  EM: "em",
  U: "u",
  S: "s",
  STRIKE: "s",
  DEL: "s",
};

// Anything that starts a new line. Each becomes a paragraph; nesting is
// flattened, because the schema has no nested blocks.
const BLOCKS = new Set([
  "P", "DIV", "BLOCKQUOTE", "PRE", "LI", "UL", "OL", "TR", "TD", "TH",
  "TABLE", "SECTION", "ARTICLE", "HEADER", "FOOTER", "MAIN", "ASIDE",
  "H1", "H2", "H3", "H4", "H5", "H6",
]);

// Dropped with their contents, rather than unwrapped: text inside these
// is not body text.
const DROPPED = new Set(["SCRIPT", "STYLE", "HEAD", "TITLE", "NOSCRIPT", "TEMPLATE", "IFRAME", "OBJECT"]);

/** The href to keep, or ``null`` when the scheme is not one we allow.
 *  A rejected link is unwrapped rather than deleted, so the text the
 *  organiser typed survives. */
function safeHref(raw: string | null): string | null {
  if (!raw) return null;
  // Control characters are how ``java\nscript:`` gets past a naive test.
  const href = raw.trim().replace(/[\u0000-\u001f\u007f]/g, "");
  return /^(?:https?:|mailto:)/i.test(href) ? href : null;
}

/** The marks a ``<span>`` or ``<font>`` is carrying as inline style.
 *  Google Docs and Word express bold as ``font-weight: 700`` rather than
 *  a tag, so a paste loses its formatting without this. */
function styleMarks(el: Element): string[] {
  const style = (el as HTMLElement).style;
  if (!style) return [];
  const marks: string[] = [];
  const weight = style.fontWeight;
  if (weight === "bold" || weight === "bolder" || Number(weight) >= 600) marks.push("strong");
  if (style.fontStyle === "italic" || style.fontStyle === "oblique") marks.push("em");
  const decoration = `${style.textDecoration} ${style.textDecorationLine}`;
  if (decoration.includes("underline")) marks.push("u");
  if (decoration.includes("line-through")) marks.push("s");
  return marks;
}

/** The element (or short chain of nested elements) one source element
 *  becomes, or ``null`` when it carries no formatting and should be
 *  unwrapped. ``outer`` is what gets appended; ``inner`` is where the
 *  children go, which differ when a single span carried two marks. */
function inlineFor(el: Element, doc: Document): { outer: HTMLElement; inner: HTMLElement } | null {
  const href = el.tagName === "A" ? safeHref(el.getAttribute("href")) : null;
  const direct = MARKS[el.tagName];
  const marks = direct ? [direct] : styleMarks(el);
  if (!href && !marks.length) return null;

  let outer: HTMLElement | null = null;
  let inner: HTMLElement | null = null;
  const push = (made: HTMLElement): void => {
    if (inner) inner.appendChild(made);
    else outer = made;
    inner = made;
  };
  if (href) {
    const anchor = doc.createElement("a");
    anchor.setAttribute("href", href);
    anchor.setAttribute("rel", LINK_REL);
    push(anchor);
  }
  for (const mark of marks) push(doc.createElement(mark));
  return { outer: outer as unknown as HTMLElement, inner: inner as unknown as HTMLElement };
}

/** Rewrite arbitrary HTML into the allowed tag set.
 *
 * Returns ``""`` for anything with no visible text, which is the same
 * call ``sanitize_richtext`` makes: an editor left holding empty
 * paragraphs stores nothing rather than ``<p></p>``.
 */
export function normalizeRichtext(html: string): string {
  const doc = new DOMParser().parseFromString(`<body>${html}</body>`, "text/html");
  const out = doc.createElement("div");

  // The paragraph currently being filled. Null means the next piece of
  // text opens a new one; a block boundary sets it back to null.
  let block: HTMLElement | null = null;
  const open = (): HTMLElement => {
    if (!block) {
      block = doc.createElement("p");
      out.appendChild(block);
    }
    return block;
  };

  // Inside a mark, everything is inline: a block that somehow ended up
  // there is flattened rather than breaking the paragraph in two.
  const walkInline = (source: Node, target: HTMLElement): void => {
    for (const child of Array.from(source.childNodes)) {
      if (child.nodeType === Node.TEXT_NODE) {
        target.appendChild(doc.createTextNode(child.nodeValue ?? ""));
        continue;
      }
      if (child.nodeType !== Node.ELEMENT_NODE) continue;
      const el = child as Element;
      if (DROPPED.has(el.tagName)) continue;
      if (el.tagName === "BR") {
        target.appendChild(doc.createElement("br"));
        continue;
      }
      const made = inlineFor(el, doc);
      if (made) {
        target.appendChild(made.outer);
        walkInline(el, made.inner);
        continue;
      }
      walkInline(el, target);
    }
  };

  const walkBlocks = (source: Node): void => {
    for (const child of Array.from(source.childNodes)) {
      if (child.nodeType === Node.TEXT_NODE) {
        if (child.nodeValue) open().appendChild(doc.createTextNode(child.nodeValue));
        continue;
      }
      if (child.nodeType !== Node.ELEMENT_NODE) continue;
      const el = child as Element;
      if (DROPPED.has(el.tagName)) continue;
      if (el.tagName === "BR") {
        open().appendChild(doc.createElement("br"));
        continue;
      }
      if (BLOCKS.has(el.tagName)) {
        // A block boundary on both sides: what came before is finished,
        // and what comes after starts a paragraph of its own.
        block = null;
        walkBlocks(el);
        block = null;
        continue;
      }
      const made = inlineFor(el, doc);
      if (made) {
        open().appendChild(made.outer);
        walkInline(el, made.inner);
        continue;
      }
      // An unformatted wrapper (span, font, anything unknown): descend
      // without ending the paragraph it sits in.
      walkBlocks(el);
    }
  };

  walkBlocks(doc.body);

  for (const paragraph of Array.from(out.children)) {
    if (!paragraph.textContent?.trim() && !paragraph.querySelector("br")) paragraph.remove();
  }
  return out.textContent?.trim() ? out.innerHTML : "";
}

/** Plain text as safe HTML, for a paste that carries no markup.
 *  Blank lines become paragraphs, single newlines become breaks. */
export function textToRichtext(text: string): string {
  const escape = (s: string): string =>
    s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  return text
    .split(/\n{2,}/)
    .map((para) => para.split("\n").map(escape).join("<br>"))
    .filter((para) => para.trim())
    .map((para) => `<p>${para}</p>`)
    .join("");
}

// A bare URL, a ``www.`` host, or an email address. Deliberately loose
// about what follows the scheme: trailing punctuation is trimmed after
// the match rather than excluded from it.
const URL_SOURCE = "(?:https?:\\/\\/|www\\.)[^\\s<>\"']+|[^\\s<>\"'@]+@[^\\s<>\"'@]+\\.[a-z]{2,}";

/** Sentence punctuation that followed the URL rather than belonging to
 *  it. A closing bracket only counts as part of the URL when the URL
 *  opened one, which is how Wikipedia links survive. */
function trimTrailing(url: string): string {
  let out = url.replace(/[.,:;!?'"]+$/, "");
  while (/[)\]}]$/.test(out)) {
    const close = out[out.length - 1];
    const openChar = { ")": "(", "]": "[", "}": "{" }[close] as string;
    const balanced = out.split(openChar).length > out.split(close).length;
    if (balanced) break;
    out = out.slice(0, -1);
  }
  return out;
}

/** The href for an autolinked run of text. */
export function autolinkHref(text: string): string {
  if (/^https?:\/\//i.test(text)) return text;
  if (text.includes("@")) return `mailto:${text}`;
  return `https://${text}`;
}

function inAnchor(node: Node | null, root: Node): boolean {
  for (let n = node; n && n !== root; n = n.parentNode) {
    if ((n as Element).tagName === "A") return true;
  }
  return false;
}

function makeAnchor(doc: Document, text: string): HTMLElement {
  const anchor = doc.createElement("a");
  anchor.setAttribute("href", autolinkHref(text));
  anchor.setAttribute("rel", LINK_REL);
  anchor.textContent = text;
  return anchor;
}

/** Link every bare URL in ``root`` that is not already inside a link.
 *  Runs on blur, which is what catches the URLs that were finished with
 *  Enter or arrived by paste rather than by typing a space. */
export function autolinkAll(root: HTMLElement): void {
  const doc = root.ownerDocument;
  const walker = doc.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const targets: Text[] = [];
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const text = node as Text;
    if (text.data.trim() && !inAnchor(text.parentNode, root)) targets.push(text);
  }

  for (const text of targets) {
    const pattern = new RegExp(URL_SOURCE, "gi");
    const fragment = doc.createDocumentFragment();
    let cursor = 0;
    for (let m = pattern.exec(text.data); m; m = pattern.exec(text.data)) {
      const url = trimTrailing(m[0]);
      if (!url) continue;
      if (m.index > cursor) fragment.appendChild(doc.createTextNode(text.data.slice(cursor, m.index)));
      fragment.appendChild(makeAnchor(doc, url));
      cursor = m.index + url.length;
      pattern.lastIndex = cursor;
    }
    if (!cursor) continue;
    if (cursor < text.data.length) fragment.appendChild(doc.createTextNode(text.data.slice(cursor)));
    text.parentNode?.replaceChild(fragment, text);
  }
}

// The same URL shapes, anchored to the end of the text before the caret.
const TRAILING_URL = new RegExp(`(?:^|[\\s\\u00a0([{<"'])(${URL_SOURCE})$`, "i");

/** Link the URL the caret just finished typing, if there is one.
 *
 * Called when a space is typed. The caret is left where the browser put
 * it, so typing continues uninterrupted. Returns whether it linked
 * anything.
 */
export function autolinkAtCaret(root: HTMLElement): boolean {
  const doc = root.ownerDocument;
  const selection = doc.defaultView?.getSelection();
  if (!selection || !selection.isCollapsed || selection.rangeCount === 0) return false;

  const node = selection.anchorNode;
  if (!node || node.nodeType !== Node.TEXT_NODE || !root.contains(node)) return false;
  if (inAnchor(node.parentNode, root)) return false;

  const text = node as Text;
  const caret = selection.anchorOffset;
  // The space that triggered this is not part of the URL.
  const typed = text.data.slice(0, caret).replace(/[\s\u00a0]+$/, "");
  const match = TRAILING_URL.exec(typed);
  if (!match) return false;

  const url = trimTrailing(match[1]);
  if (!url) return false;
  const start = typed.length - match[1].length;
  const end = start + url.length;

  const fragment = doc.createDocumentFragment();
  if (start > 0) fragment.appendChild(doc.createTextNode(text.data.slice(0, start)));
  fragment.appendChild(makeAnchor(doc, url));
  const tail = doc.createTextNode(text.data.slice(end));
  fragment.appendChild(tail);
  text.parentNode?.replaceChild(fragment, text);

  const range = doc.createRange();
  range.setStart(tail, Math.max(0, Math.min(caret - end, tail.data.length)));
  range.collapse(true);
  selection.removeAllRanges();
  selection.addRange(range);
  return true;
}

/** The ``<a>`` the node sits in, or ``null``. The editor uses it both to
 *  light the toolbar button and to select a whole link before replacing
 *  it, so clicking anywhere in a link edits all of it. */
export function anchorAt(node: Node | null, root: HTMLElement): HTMLElement | null {
  for (let n = node; n && n !== root; n = n.parentNode) {
    if ((n as Element).tagName === "A") return n as HTMLElement;
  }
  return null;
}

/** Whether the field should show its placeholder.
 *
 * No visible text, and no more than one line. Deleting everything
 * usually leaves the browser holding an empty paragraph, which still
 * counts as empty; pressing Enter on an empty field leaves two, which
 * does not, because the caret has visibly moved.
 */
export function isEditorEmpty(root: HTMLElement): boolean {
  if (root.textContent?.trim()) return false;
  return root.querySelectorAll("p, div").length <= 1;
}
