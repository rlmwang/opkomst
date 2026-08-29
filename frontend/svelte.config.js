import { vitePreprocess } from "@sveltejs/vite-plugin-svelte";

/**
 * Svelte's build settings. ``vitePreprocess`` is what lets a component
 * write ``<script lang="ts">`` and scoped ``<style>`` the way the Vue
 * components next to it do.
 */
export default { preprocess: vitePreprocess() };
