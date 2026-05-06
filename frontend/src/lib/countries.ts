/**
 * Curated country list for the WhatsApp blast tool's
 * country-code dropdown.
 *
 * The list is deliberately Europe-heavy with a few global
 * additions: this app is used by a Dutch socialist organising
 * group whose members are overwhelmingly in NL, with adjacent
 * EU countries and a long-tail of diaspora cases. Adding a new
 * row is one line; we'd rather omit obvious-spam destinations
 * than dump the whole ITU list and bury the common cases.
 *
 * ``flagEmoji`` derives the Unicode regional-indicator pair
 * from the ISO-3166 alpha-2 code at runtime, so we don't have
 * to maintain a parallel table of flag glyphs.
 */

export interface Country {
  /** ISO-3166 alpha-2 country code. Drives the flag emoji. */
  iso: string;
  /** International dial code, digits only (no leading "+"). */
  dialCode: string;
  /** Display name. English; the dropdown shows the same string
   * regardless of UI locale because country names are widely
   * recognisable in their English form, and shipping a
   * locale-dependent country list is more work than this tool
   * justifies. */
  name: string;
}

export const COUNTRIES: Country[] = [
  { iso: "NL", dialCode: "31", name: "Netherlands" },
  { iso: "BE", dialCode: "32", name: "Belgium" },
  { iso: "DE", dialCode: "49", name: "Germany" },
  { iso: "FR", dialCode: "33", name: "France" },
  { iso: "GB", dialCode: "44", name: "United Kingdom" },
  { iso: "IE", dialCode: "353", name: "Ireland" },
  { iso: "LU", dialCode: "352", name: "Luxembourg" },
  { iso: "ES", dialCode: "34", name: "Spain" },
  { iso: "PT", dialCode: "351", name: "Portugal" },
  { iso: "IT", dialCode: "39", name: "Italy" },
  { iso: "AT", dialCode: "43", name: "Austria" },
  { iso: "CH", dialCode: "41", name: "Switzerland" },
  { iso: "DK", dialCode: "45", name: "Denmark" },
  { iso: "SE", dialCode: "46", name: "Sweden" },
  { iso: "NO", dialCode: "47", name: "Norway" },
  { iso: "FI", dialCode: "358", name: "Finland" },
  { iso: "IS", dialCode: "354", name: "Iceland" },
  { iso: "PL", dialCode: "48", name: "Poland" },
  { iso: "CZ", dialCode: "420", name: "Czech Republic" },
  { iso: "SK", dialCode: "421", name: "Slovakia" },
  { iso: "HU", dialCode: "36", name: "Hungary" },
  { iso: "RO", dialCode: "40", name: "Romania" },
  { iso: "BG", dialCode: "359", name: "Bulgaria" },
  { iso: "GR", dialCode: "30", name: "Greece" },
  { iso: "HR", dialCode: "385", name: "Croatia" },
  { iso: "SI", dialCode: "386", name: "Slovenia" },
  { iso: "EE", dialCode: "372", name: "Estonia" },
  { iso: "LV", dialCode: "371", name: "Latvia" },
  { iso: "LT", dialCode: "370", name: "Lithuania" },
  { iso: "MT", dialCode: "356", name: "Malta" },
  { iso: "CY", dialCode: "357", name: "Cyprus" },
  { iso: "US", dialCode: "1", name: "United States" },
  { iso: "CA", dialCode: "1", name: "Canada" },
  { iso: "AU", dialCode: "61", name: "Australia" },
  { iso: "NZ", dialCode: "64", name: "New Zealand" },
  { iso: "TR", dialCode: "90", name: "Türkiye" },
  { iso: "UA", dialCode: "380", name: "Ukraine" },
  { iso: "RU", dialCode: "7", name: "Russia" },
  { iso: "MA", dialCode: "212", name: "Morocco" },
  { iso: "IL", dialCode: "972", name: "Israel" },
  { iso: "AE", dialCode: "971", name: "United Arab Emirates" },
  { iso: "SA", dialCode: "966", name: "Saudi Arabia" },
  { iso: "IN", dialCode: "91", name: "India" },
  { iso: "ID", dialCode: "62", name: "Indonesia" },
  { iso: "ZA", dialCode: "27", name: "South Africa" },
  { iso: "BR", dialCode: "55", name: "Brazil" },
  { iso: "AR", dialCode: "54", name: "Argentina" },
  { iso: "MX", dialCode: "52", name: "Mexico" },
];

/** Map an ISO-3166 alpha-2 code to its emoji flag by mapping
 * each letter to its corresponding regional-indicator symbol
 * (U+1F1E6 = 🇦, etc.). Works in every browser that renders
 * RGI-flag sequences (i.e. all of them, modulo a few corporate
 * Windows builds). */
export function flagEmoji(iso: string): string {
  return iso
    .toUpperCase()
    .split("")
    .map((c) => String.fromCodePoint(0x1f1e6 + c.charCodeAt(0) - 0x41))
    .join("");
}
