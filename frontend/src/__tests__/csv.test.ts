import { describe, expect, it } from "vitest";
import { applyMerge, mergeTags, normalisePhone, parseCsv } from "@/lib/csv";

describe("parseCsv", () => {
  it("parses a simple header + two rows with the default phone column", () => {
    const r = parseCsv("number,name\n31612345678,Alice\n31698765432,Bob");
    expect(r.fatal).toEqual([]);
    expect(r.headers).toEqual(["number", "name"]);
    expect(r.rows).toHaveLength(2);
    expect(r.rows[0]).toMatchObject({
      phone: "31612345678",
      status: "ok",
      fields: { number: "31612345678", name: "Alice" },
    });
  });

  it("lowercases header names so 'Number' and 'NAME' work", () => {
    const r = parseCsv("Number,NAME\n31612345678,Alice");
    expect(r.headers).toEqual(["number", "name"]);
    expect(r.rows[0].fields).toEqual({ number: "31612345678", name: "Alice" });
  });

  it("accepts a custom phone-column name", () => {
    const r = parseCsv("phone,name\n31612345678,Alice", "phone");
    expect(r.fatal).toEqual([]);
    expect(r.rows[0]).toMatchObject({ phone: "31612345678", status: "ok" });
  });

  it("matches the phone-column name case-insensitively", () => {
    const r = parseCsv("Telefoon,naam\n31612345678,Alice", "TELEFOON");
    expect(r.fatal).toEqual([]);
    expect(r.rows[0].phone).toBe("31612345678");
  });

  it("applies a default country code to bare national numbers", () => {
    const r = parseCsv("number,name\n0612345678,Alice\n612345678,Bob", "number", "31");
    expect(r.rows.map((row) => row.phone)).toEqual(["31612345678", "31612345678"]);
    // The two normalise to the same digits, so the second row trips
    // the duplicate guard.
    expect(r.rows[0].status).toBe("ok");
    expect(r.rows[1]).toMatchObject({ status: "invalid", error: "duplicateNumber" });
  });

  it("does not double-prefix numbers that already carry the country code", () => {
    const r = parseCsv("number,name\n31612345678,Alice\n+31612345678,Bob", "number", "31");
    expect(r.rows[0].phone).toBe("31612345678");
    expect(r.rows[1].phone).toBe("31612345678");
  });

  it("strips a leading 00 international prefix", () => {
    const r = parseCsv("number,name\n0031612345678,Alice");
    expect(r.rows[0].phone).toBe("31612345678");
  });

  it("emits missingPhoneColumn when the named column isn't in the header", () => {
    const r = parseCsv("foo,bar\n1,2", "phone");
    expect(r.fatal).toEqual(["missingPhoneColumn"]);
    expect(r.rows).toEqual([]);
  });

  it("emits emptyInput on blank text", () => {
    expect(parseCsv("").fatal).toEqual(["emptyInput"]);
    expect(parseCsv("   \n  ").fatal).toEqual(["emptyInput"]);
  });

  it("normalises phone numbers by stripping +, spaces, dashes, parens", () => {
    const r = parseCsv("number,name\n+31 (6) 12-345-678,Alice");
    expect(r.rows[0].phone).toBe("31612345678");
    expect(r.rows[0].status).toBe("ok");
  });

  it("flags too-short and too-long numbers as invalidNumber", () => {
    const r = parseCsv(
      "number,name\n123,Short\n12345678901234567,Long\n31612345678,Ok",
    );
    expect(r.rows.map((row) => row.status)).toEqual(["invalid", "invalid", "ok"]);
    expect(r.rows[0].error).toBe("invalidNumber");
    expect(r.rows[1].error).toBe("invalidNumber");
  });

  it("flags an empty number cell as emptyNumber", () => {
    const r = parseCsv("number,name\n,NoNumber");
    expect(r.rows[0]).toMatchObject({ status: "invalid", error: "emptyNumber" });
  });

  it("flags duplicates after the first occurrence", () => {
    const r = parseCsv("number,name\n31612345678,Alice\n31612345678,Bob");
    expect(r.rows[0].status).toBe("ok");
    expect(r.rows[1]).toMatchObject({ status: "invalid", error: "duplicateNumber" });
  });

  it("auto-detects TSV when the header row contains tabs (Google Sheets paste)", () => {
    const r = parseCsv("number\tname\tcolor\n31612345678\tAlice\tred\n31698765432\tBob\tblue");
    expect(r.fatal).toEqual([]);
    expect(r.headers).toEqual(["number", "name", "color"]);
    expect(r.rows).toHaveLength(2);
    expect(r.rows[0].fields).toEqual({
      number: "31612345678",
      name: "Alice",
      color: "red",
    });
  });

  it("treats commas inside cells as data when the file is TSV", () => {
    // A name like "Doe, John" with a literal comma must survive
    // because TSV uses tabs as the field separator.
    const r = parseCsv("number\tname\n31612345678\tDoe, John");
    expect(r.rows[0].fields.name).toBe("Doe, John");
  });

  it("respects RFC-4180 quoting so embedded commas survive", () => {
    const r = parseCsv('number,name\n31612345678,"Doe, John"');
    expect(r.rows[0].fields.name).toBe("Doe, John");
  });

  it("decodes doubled quotes inside quoted cells", () => {
    const r = parseCsv('number,name\n31612345678,"He said ""hi"""');
    expect(r.rows[0].fields.name).toBe('He said "hi"');
  });

  it("handles CRLF newlines", () => {
    const r = parseCsv("number,name\r\n31612345678,Alice\r\n31698765432,Bob\r\n");
    expect(r.rows).toHaveLength(2);
  });

  it("skips trailing blank lines without emitting phantom rows", () => {
    const r = parseCsv("number,name\n31612345678,Alice\n\n\n");
    expect(r.rows).toHaveLength(1);
  });

  it("strips a leading UTF-8 BOM", () => {
    const r = parseCsv("﻿number,name\n31612345678,Alice");
    expect(r.headers[0]).toBe("number");
    expect(r.rows[0].status).toBe("ok");
  });
});

describe("normalisePhone", () => {
  it("strips whitespace, plus, dashes, parens, and dots", () => {
    expect(normalisePhone("+31 (6) 12-345.678")).toBe("31612345678");
  });

  it("returns digits unchanged when no country code is supplied", () => {
    expect(normalisePhone("31612345678")).toBe("31612345678");
  });

  it("replaces a leading 0 with the country code when supplied", () => {
    expect(normalisePhone("0612345678", "31")).toBe("31612345678");
  });

  it("prepends the country code when the number has no national prefix", () => {
    expect(normalisePhone("612345678", "31")).toBe("31612345678");
  });

  it("leaves the number alone when it already starts with the country code", () => {
    expect(normalisePhone("31612345678", "31")).toBe("31612345678");
  });

  it("accepts a country code given with a leading +", () => {
    expect(normalisePhone("0612345678", "+31")).toBe("31612345678");
  });

  it("drops a leading 00 international prefix even without a country code", () => {
    expect(normalisePhone("0031612345678")).toBe("31612345678");
  });

  it("returns an empty string for empty input", () => {
    expect(normalisePhone("", "31")).toBe("");
  });
});

describe("mergeTags", () => {
  it("excludes the default 'number' column", () => {
    expect(mergeTags(["number", "name", "color"])).toEqual(["name", "color"]);
  });

  it("excludes whatever column was chosen as the phone column", () => {
    expect(mergeTags(["phone", "name", "color"], "phone")).toEqual(["name", "color"]);
  });

  it("matches case-insensitively when filtering the phone column", () => {
    expect(mergeTags(["phone", "name"], "PHONE")).toEqual(["name"]);
  });
});

describe("applyMerge", () => {
  it("substitutes {tag} placeholders from row fields", () => {
    expect(applyMerge("Hi {name}, your color is {color}.", { name: "Alice", color: "red" })).toBe(
      "Hi Alice, your color is red.",
    );
  });

  it("leaves unknown tags untouched so the user sees their typo", () => {
    expect(applyMerge("Hi {nme}", { name: "Alice" })).toBe("Hi {nme}");
  });

  it("matches tags case-insensitively against lowercased field keys", () => {
    expect(applyMerge("Hi {NAME}", { name: "Alice" })).toBe("Hi Alice");
  });

  it("supports multiple occurrences of the same tag", () => {
    expect(applyMerge("{name} and {name}", { name: "Alice" })).toBe("Alice and Alice");
  });
});
