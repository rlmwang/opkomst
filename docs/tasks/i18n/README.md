# Taking the organiser app off vue-i18n

**Landed.** The organiser critical path went from 100,321 gz to
**81,907 gz**, a saving of 18,414. Nothing in `dist` mentions intlify,
the `en` catalogue is still fetched on demand, and all 811 call sites
are unchanged. What follows is the record.

One task. `vue-i18n` and `@intlify` are **18,760 gz** in the organiser
app's critical path, which is 19% of it, and the app uses three things
from them.

The replacement already exists and is already shipping:
`src/public/i18n.ts` is what the public mini-apps do instead, and has
done since they were written, for exactly this reason. This task brings
the organiser app to the same place without touching a single `t()`
call.

## What the app actually uses

Counted, not guessed:

| | count |
|---|---|
| `t()` call sites | 811 |
| `useI18n()` call sites | 58 |
| destructures of `t` | 54 |
| destructures of `locale` | 18 |
| destructures of `te` | 2 |
| `$t` in templates | 0 |
| keys per catalogue | 907, in both |
| strings with `{param}` | 109 |
| strings with `@:linked` | 2 |
| plural forms (`one \| other`) | 0 |

Nothing calls `d()`, `n()`, `tm()` or `rt()`. There are no plurals, no
date or number formatting, no message compiler at runtime, no
`legacy: true`. What is being paid for is a dotted-path lookup, brace
interpolation, and a reactive current language.

## The shape to end on

**Keep both JSON catalogues and every call site.** 907 keys and 811
calls is not a rewrite anybody should sign up for, and there is nothing
wrong with the catalogues. `src/i18n.ts` grows a `t` of its own and
everything upstream of it stays as it is.

What `src/i18n.ts` has to keep exporting, unchanged in signature:

- `t(key, params?)`, reading the current language and falling back to
  Dutch. Reads `locale.value`, so it stays a reactive dependency and a
  language switch still repaints.
- `te(key)`, which only `useFormText` uses, for its
  `<resource>.<key>` then `form.<key>` fallback.
- `locale`, a `Ref<Locale>`.
- `setLocale`, `loadLocale`, `initI18n`, all as they are.
- `useI18n()`, ours, returning `{ t, te, locale }`. Every one of the 58
  call sites keeps its import and its destructure.

Three details that are load-bearing:

1. **The missing-key tripwire stays.** `missingKeyHandler` returns
   `[key]` so a miss is visible on screen, warns in dev and reports to
   Sentry in prod once per key. It caught the `usersTitle` regression
   and it is not optional. Ours does the same thing, and is simpler
   because it is one `if` rather than a plugin hook.
2. **The two `@:appName` messages become `{appName}`.** Linked messages
   are a whole feature for two strings. `t` merges
   `{ appName: APP_NAME }` into every params object, so the two strings
   change and nothing else does.
3. **The bundled-default, fetched-rest split stays exactly as it is.**
   `nl` is imported, `en` is a dynamic import, `loaded` is a `Set`. That
   design is explained at length in `src/i18n.ts` and the reasoning does
   not change.

Six test files build their own `createI18n({ messages: {...} })`. They
get a small helper instead. That is the only test change.

## Phases

**1. Write it.** `t`, `te`, and `useI18n` in `src/i18n.ts`, against the
existing catalogues. This is roughly 60 lines: a dotted-path walk, a
`{param}` replace, the fallback chain, and the missing handler that is
already written.

**2. Swap.** Delete the `createI18n` block, the `vue-i18n` import, and
`app.use(i18n)` in `main.ts`. Six test files take the helper. Nothing
in `src/pages` or `src/components` changes.

**3. Measure and remove.** `npm uninstall vue-i18n`, rebuild, record
the before and after in the commit message the way the PrimeVue series
did. Confirm nothing in `dist` mentions intlify.

**Done when:** every string still renders, the language switch still
works without a reload, `en` still arrives on demand and is still
cached, a deliberately misspelled key still shows `[the.key]` and still
reaches Sentry, and `i18n-*.js` is gone from the entry.

## Before calling it done

`npx vue-tsc --noEmit`, `npx vitest run`, `npm run build`,
`uv run python scripts/check_brand_tokens.py`.

## What was not in the plan

**`t(key, 1, { locale })`.** Six call sites in `EventFormPage` used
vue-i18n's third argument to render a string in a named language rather
than the one on screen: the event form seeds its default sign-up
options in the *event's* language, which is not necessarily the
organiser's. The `1` was a plural count that meant nothing.

That is now `tIn(loc, key)`, which says what it does. It also exposed a
bug the old call had: `en` is fetched, not bundled, so an organiser
reading Dutch and creating an English event got Dutch defaults, silently,
through the fallback. `EventFormPage` now asks for both catalogues at
setup, which it can do without waiting because the switch that needs the
second one is a click away.

**`setCatalogue`.** Installing a catalogue is now a named export rather
than a plugin method, which is what `loadLocale` uses and what the six
tests use through `src/__tests__/i18n-harness.ts`.

## Worth knowing

This is worth doing whether or not the app later moves off Vue
(`docs/tasks/svelte/README.md`). It removes a framework-coupled
dependency and replaces it with 60 lines that port unchanged, so it
makes that migration smaller rather than larger. Do it first.
