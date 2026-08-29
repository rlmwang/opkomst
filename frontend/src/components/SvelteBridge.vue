<script setup lang="ts">
/**
 * One Svelte component, rendered inside a Vue one.
 *
 * The organiser app is a single entry, so its pages cannot cross to
 * Svelte a few at a time on their own: a Vue parent cannot render a
 * Svelte child. This is the glue that lets them move one at a time,
 * with every commit in between building and working
 * (``docs/tasks/svelte``).
 *
 * This direction rather than the other on purpose. The router is the
 * one thing every page reaches for (``useRouter``, ``useRoute``), so it
 * has to be the last thing to cross, which means the shell stays Vue
 * and the pages under it move first. The boundary is the route: a
 * ported page gets one wrapper, and nothing inside it needs one.
 *
 * Temporary by construction. When the last ``.vue`` under ``src/`` goes,
 * so does this file, and no call site is left holding anything: a
 * ``<SvelteBridge :component="X" :props="p" />`` becomes ``<X {...p} />``
 * in a Svelte parent.
 *
 * Events come back as callbacks inside the props (``onthing``), which is
 * Svelte 5's own shape, so the child needs no adapter either.
 */
import type { Component } from "svelte";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";

import { mountBridged } from "@/lib/svelte-bridge.svelte";

const props = defineProps<{
  component: Component<Record<string, unknown>>;
  props?: Record<string, unknown>;
}>();

const host = ref<HTMLElement>();
let bridged: ReturnType<typeof mountBridged> | null = null;

onMounted(() => {
  if (host.value) bridged = mountBridged(host.value, props.component, props.props ?? {});
});

// ``deep`` because the parent rebuilds the props object on every render
// and its contents are what the child reads.
watch(
  () => props.props,
  (next) => bridged?.update(next ?? {}),
  { deep: true },
);

onBeforeUnmount(() => {
  bridged?.destroy();
  bridged = null;
});
</script>

<template>
  <!-- ``display: contents`` so the wrapper is not a box: the child sits
       in the parent's layout exactly where the Vue component it
       replaced did. -->
  <div ref="host" style="display: contents"></div>
</template>
