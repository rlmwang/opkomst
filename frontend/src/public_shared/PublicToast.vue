<script setup lang="ts">
/** Renders the public-app toast queue (see ``publicToast.ts``). Mounted
 *  once in PublicShell so every public page shares one toast region. */
import { usePublicToasts } from "./publicToast";

const state = usePublicToasts();
</script>

<template>
  <div class="toast-region" aria-live="assertive" role="alert">
    <TransitionGroup name="toast">
      <div v-for="t in state.toasts" :key="t.id" class="toast">{{ t.message }}</div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toast-region {
  position: fixed;
  top: 1rem;
  left: 50%;
  transform: translateX(-50%);
  z-index: 1000;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  align-items: center;
  pointer-events: none;
  width: max-content;
  max-width: 90vw;
}
.toast {
  background: var(--brand-red);
  color: #fff;
  padding: 0.625rem 1rem;
  border-radius: 8px;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.18);
  font-size: 0.9375rem;
  line-height: 1.35;
  text-align: center;
}
.toast-enter-active,
.toast-leave-active {
  transition: opacity 180ms ease, transform 180ms ease;
}
.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateY(-0.5rem);
}
</style>
