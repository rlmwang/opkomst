/**
 * The three functions this app asks of Sentry, named.
 *
 * ``lib/sentry.ts`` fetches Sentry after mount, and a dynamic import of
 * the whole package defeats tree-shaking: Rollup cannot know which
 * properties of a namespace object get read, so it keeps everything.
 * That pulled in tracing, session replay, user feedback and metrics,
 * none of which this app uses, and turned a 31 kB dependency into a
 * 153 kB one.
 *
 * Naming the exports statically here, and making this file the thing
 * that gets imported dynamically, puts the tree-shaking boundary back
 * where it belongs.
 */
export { captureException, captureMessage, init } from "@sentry/vue";
