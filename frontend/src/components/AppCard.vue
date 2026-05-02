<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    /** Apply the standard `.stack` vertical-gap layout. Default true. */
    stack?: boolean;
    /** Underlying tag — switch to `form`, `section`, etc. when needed. */
    tag?: string;
  }>(),
  { stack: true, tag: "div" },
);
</script>

<template>
  <component :is="props.tag" :class="['card', { stack: props.stack }]">
    <slot />
  </component>
</template>
