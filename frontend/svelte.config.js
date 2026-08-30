import { vitePreprocess } from "@sveltejs/vite-plugin-svelte";

/**
 * Svelte's build settings. ``vitePreprocess`` is what lets a component
 * write ``<script lang="ts">``, so the compiler hands the TypeScript to
 * Vite rather than choking on it.
 */
export default { preprocess: vitePreprocess() };
