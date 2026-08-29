import { describe, expect, it } from "vitest";

import { autolinkHref, isEditorEmpty, normalizeRichtext, textToRichtext } from "@/lib/richtext";

// The editor is the browser's own contenteditable, so the markup it
// hands back differs per browser and is arbitrary after a paste. These
// pin the rewrite that turns any of it into the tag set
// ``backend/services/sanitize.py`` accepts.

describe("normalizeRichtext", () => {
  it("maps every tag a browser might emit onto the allowed mark", () => {
    expect(normalizeRichtext("<p><b>a</b> <i>b</i> <u>c</u> <strike>d</strike> <del>e</del></p>")).toBe(
      "<p><strong>a</strong> <em>b</em> <u>c</u> <s>d</s> <s>e</s></p>",
    );
  });

  it("turns every block into a paragraph and flattens nesting", () => {
    expect(normalizeRichtext("<div>one</div><div>two</div>")).toBe("<p>one</p><p>two</p>");
    expect(normalizeRichtext("<ul><li>one</li><li>two</li></ul>")).toBe("<p>one</p><p>two</p>");
    expect(normalizeRichtext("<h2>title</h2>body")).toBe("<p>title</p><p>body</p>");
  });

  it("wraps bare text in a paragraph without breaking it up", () => {
    expect(normalizeRichtext("bare <b>text</b> here")).toBe("<p>bare <strong>text</strong> here</p>");
  });

  it("keeps a span from splitting the paragraph it sits in", () => {
    expect(normalizeRichtext("<p>a<span>b</span>c</p>")).toBe("<p>abc</p>");
  });

  it("reads the marks Google Docs and Word express as inline style", () => {
    expect(normalizeRichtext('<p><span style="font-weight:700">a</span></p>')).toBe("<p><strong>a</strong></p>");
    expect(normalizeRichtext('<p><span style="font-style:italic">a</span></p>')).toBe("<p><em>a</em></p>");
    expect(normalizeRichtext('<p><span style="text-decoration:line-through">a</span></p>')).toBe("<p><s>a</s></p>");
  });

  it("nests a span that carried two marks at once", () => {
    const html = normalizeRichtext('<p><span style="font-weight:bold;font-style:italic">a</span></p>');
    expect(html).toBe("<p><strong><em>a</em></strong></p>");
  });

  it("keeps safe links and stamps the rel", () => {
    expect(normalizeRichtext('<p><a href="https://x.nl">x</a></p>')).toBe(
      '<p><a href="https://x.nl" rel="nofollow noopener noreferrer">x</a></p>',
    );
    expect(normalizeRichtext('<p><a href="mailto:a@b.nl">a</a></p>')).toContain('href="mailto:a@b.nl"');
  });

  it("unwraps a link whose scheme is not allowed, keeping the text", () => {
    expect(normalizeRichtext('<p><a href="javascript:alert(1)">click</a></p>')).toBe("<p>click</p>");
    expect(normalizeRichtext('<p><a href="/relative">click</a></p>')).toBe("<p>click</p>");
  });

  it("drops every attribute other than the link href", () => {
    expect(normalizeRichtext('<p class="x" id="y" onclick="e()">a</p>')).toBe("<p>a</p>");
    expect(normalizeRichtext('<b style="color:red">a</b>')).toBe("<p><strong>a</strong></p>");
  });

  it("removes script and style with their contents", () => {
    expect(normalizeRichtext("<p>a</p><script>alert(1)<\/script>")).toBe("<p>a</p>");
    expect(normalizeRichtext("<style>p{color:red}</style><p>a</p>")).toBe("<p>a</p>");
  });

  it("keeps line breaks", () => {
    expect(normalizeRichtext("<p>a<br>b</p>")).toBe("<p>a<br>b</p>");
  });

  it("collapses anything with no visible text to the empty string", () => {
    expect(normalizeRichtext("")).toBe("");
    expect(normalizeRichtext("<p></p>")).toBe("");
    expect(normalizeRichtext("<p><br></p>")).toBe("");
    expect(normalizeRichtext("<p>   </p>")).toBe("");
  });

  it("is idempotent, so re-editing a saved body does not change it", () => {
    const once = normalizeRichtext('<div><b>a</b> <a href="https://x.nl">x</a></div>');
    expect(normalizeRichtext(once)).toBe(once);
  });
});

describe("textToRichtext", () => {
  it("splits blank lines into paragraphs and single ones into breaks", () => {
    expect(textToRichtext("a\nb\n\nc")).toBe("<p>a<br>b</p><p>c</p>");
  });

  it("escapes markup in pasted plain text", () => {
    expect(textToRichtext("<b>a</b>")).toBe("<p>&lt;b&gt;a&lt;/b&gt;</p>");
  });
});

describe("autolinkHref", () => {
  it("leaves a full URL alone and completes the other shapes", () => {
    expect(autolinkHref("https://x.nl/a")).toBe("https://x.nl/a");
    expect(autolinkHref("www.x.nl")).toBe("https://www.x.nl");
    expect(autolinkHref("a@b.nl")).toBe("mailto:a@b.nl");
  });
});

describe("isEditorEmpty", () => {
  const el = (html: string): HTMLElement => {
    const node = document.createElement("div");
    node.innerHTML = html;
    return node;
  };

  it("is empty while there is no text and one line at most", () => {
    expect(isEditorEmpty(el(""))).toBe(true);
    // What the browser leaves behind when everything is deleted.
    expect(isEditorEmpty(el("<p><br></p>"))).toBe(true);
  });

  it("is not empty once there is text, or a second line", () => {
    expect(isEditorEmpty(el("<p>a</p>"))).toBe(false);
    // Enter pressed on an empty field: the caret has visibly moved.
    expect(isEditorEmpty(el("<p><br></p><p><br></p>"))).toBe(false);
  });
});
