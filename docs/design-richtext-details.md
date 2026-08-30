# Rich text in the details field

The description of an event, questionnaire, date poll or roster is rich
text: bold, italic, underline, strikethrough and links. No lists, no
headings, no nesting.

There is no editor library. `RichTextField.vue` is the browser's own
`contenteditable`, driven by `document.execCommand`, which does all five
marks on its own. Tiptap and ProseMirror used to sit here and cost
114 kB gzipped, most of it machinery for block structure this field does
not have.

Two things the browser does badly are handled in `lib/richtext.ts`.
`normalizeRichtext` rewrites the markup on the way out, because browsers
disagree about what they emit for the same keystroke (`<b>` or
`<strong>`, `<div>` or `<p>`) and a paste carries whatever Word felt
like writing. `autolinkAtCaret` and `autolinkAll` turn a typed URL into
a link, on the space that finishes it and again on blur.

What the browser does badly and nothing here fixes: text entry on phones
using a Chinese, Japanese or Korean keyboard. A large part of
ProseMirror existed for that, and it is the place to look first if the
field ever misbehaves on mobile.

What the editor produces is stored as HTML and sanitised on the way in,
on the server, against a small allowlist of tags and attributes: no
styles, no classes, no scripts, and every link forced to
`rel="nofollow noopener noreferrer"`. `services/sanitize.py` is the
whole rule, and the public pages render what it returned. The client
cleanup targets that same list, so a body does not change shape the
first time it is saved.

Plain text stays plain. A description somebody typed without touching a
button is stored as the paragraph it is, so nothing that never used the
editor carries markup it did not ask for.
