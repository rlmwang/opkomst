import { describe, expect, it } from "vitest";
import { whatsappFormat } from "@/lib/whatsappFormat";

describe("whatsappFormat", () => {
  it("escapes raw HTML before applying formatting", () => {
    expect(whatsappFormat("<script>alert(1)</script>")).toBe(
      "&lt;script&gt;alert(1)&lt;/script&gt;",
    );
  });

  it("converts *bold* into <strong>", () => {
    expect(whatsappFormat("hello *world*")).toBe("hello <strong>world</strong>");
  });

  it("converts _italic_ into <em>", () => {
    expect(whatsappFormat("come _on_ now")).toBe("come <em>on</em> now");
  });

  it("converts ~strike~ into <s>", () => {
    expect(whatsappFormat("oh ~no~")).toBe("oh <s>no</s>");
  });

  it("converts `monospace` into <code>", () => {
    expect(whatsappFormat("run `npm test`")).toBe("run <code>npm test</code>");
  });

  it("supports triple-backtick code blocks", () => {
    expect(whatsappFormat("```block```")).toBe("<code>block</code>");
  });

  it("does not re-interpret emphasis tokens that fall inside code", () => {
    expect(whatsappFormat("`*literal*`")).toBe("<code>*literal*</code>");
  });

  it("converts newlines to <br>", () => {
    expect(whatsappFormat("line one\nline two")).toBe("line one<br>line two");
  });

  it("leaves plain text untouched", () => {
    expect(whatsappFormat("hello world")).toBe("hello world");
  });

  it("escapes ampersands and quotes", () => {
    expect(whatsappFormat('A & B "quoted"')).toBe("A &amp; B &quot;quoted&quot;");
  });

  it("does not bold a snake_case identifier as italic", () => {
    expect(whatsappFormat("foo_bar_baz")).toBe("foo_bar_baz");
  });
});
