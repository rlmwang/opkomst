/**
 * App-wide brand constants. One source of truth so a rename
 * doesn't require sweeping every component + locale string by
 * hand. ``i18n.ts`` injects ``APP_NAME`` into both locales as
 * ``appName`` so messages can use ``@:appName`` to interpolate
 * without each ``t()`` call having to pass it explicitly.
 */
export const APP_NAME = "opkomst.nu";
