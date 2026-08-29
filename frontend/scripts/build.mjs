/**
 * Build the app in two passes, one per half.
 *
 * The organiser app and the seven public mini-apps used to be eight
 * entries in one Rollup graph. That is the right shape while they share
 * a framework runtime and little else, and it was the shape all through
 * the Vue years. It stopped being right the moment both halves were
 * drawn by the same Svelte components: a module two entries can reach
 * goes into a chunk they must both download, so every public page began
 * paying four to six kilobytes for the organiser app's share of it.
 *
 * A stranger opening a sign-up link on mobile data is who the public
 * pages are for, so they get their own graph and their own chunks. The
 * two passes write into one directory: the public pass empties it, the
 * organiser pass adds to it. Asset names are content-hashed, so a file
 * both passes emit lands on the same name and the second write is
 * identical to the first.
 */
import { build } from "vite";

const outDirArg = process.argv.indexOf("--outDir");
const outDir = outDirArg === -1 ? "dist" : process.argv[outDirArg + 1];

for (const [entries, emptyOutDir] of [
  ["public", true],
  ["app", false],
]) {
  process.env.BUILD_ENTRIES = entries;
  await build({ build: { outDir, emptyOutDir } });
}
