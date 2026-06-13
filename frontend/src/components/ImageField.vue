<script setup lang="ts">
import Button from "primevue/button";
import InputText from "primevue/inputtext";
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import { ApiError } from "@/api/client";
import { useImageUpload } from "@/composables/useImageUpload";
import { useToasts } from "@/lib/toasts";

/** Shared hero-image block for the organiser edit pages (events,
 *  forms, datepolls): a 4:5 preview with upload / replace / remove,
 *  plus the optional artist-credit handle. Upload only works once the
 *  row exists (it needs an id), so in create mode it shows a hint and
 *  the picker is hidden — the artist handle is still editable so it
 *  can be saved with the create. ``imageUrl`` is display-only (the
 *  upload endpoint persists it); ``artist`` feeds the create/update
 *  payload. */
const props = defineProps<{ resource: string; entityId: string | null }>();
const imageUrl = defineModel<string | null>("imageUrl", { required: true });
const artist = defineModel<string | null>("artist", { required: true });

const { t } = useI18n();
const toasts = useToasts();
const { upload, remove } = useImageUpload(props.resource);

const uploading = ref(false);
const fileInput = ref<HTMLInputElement | null>(null);

function pick(): void {
  fileInput.value?.click();
}

function describeError(err: unknown): string {
  if (err instanceof ApiError) return `${err.status} ${err.message}`;
  if (err instanceof Error && err.message) return err.message;
  return "unknown";
}

async function onSelected(ev: Event): Promise<void> {
  const input = ev.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = ""; // allow re-picking the same file
  if (!file || !props.entityId) return;
  uploading.value = true;
  try {
    const updated = await upload.mutateAsync({ id: props.entityId, file });
    imageUrl.value = updated.image_url;
    toasts.success(t("imageField.uploaded"));
  } catch (err) {
    toasts.error(`${t("imageField.uploadFailed")}: ${describeError(err)}`);
  } finally {
    uploading.value = false;
  }
}

async function removeImage(): Promise<void> {
  if (!props.entityId) return;
  uploading.value = true;
  try {
    const updated = await remove.mutateAsync(props.entityId);
    imageUrl.value = updated.image_url;
  } catch (err) {
    toasts.error(`${t("imageField.removeFailed")}: ${describeError(err)}`);
  } finally {
    uploading.value = false;
  }
}
</script>

<template>
  <section class="form-section">
    <h2 class="section-heading">{{ t("imageField.heading") }}</h2>
    <input
      ref="fileInput"
      type="file"
      accept="image/jpeg,image/png,image/webp"
      style="display: none"
      @change="onSelected"
    />
    <div v-if="!entityId" class="muted">{{ t("imageField.createFirst") }}</div>
    <div v-else-if="imageUrl" class="image-preview">
      <img :src="imageUrl" :alt="t('imageField.alt')" />
      <div class="image-actions">
        <Button
          type="button"
          :label="t('imageField.replace')"
          icon="pi pi-refresh"
          size="small"
          severity="secondary"
          :disabled="uploading"
          @click="pick"
        />
        <Button
          type="button"
          :label="t('imageField.remove')"
          icon="pi pi-trash"
          size="small"
          severity="secondary"
          text
          :disabled="uploading"
          @click="removeImage"
        />
      </div>
    </div>
    <Button
      v-else
      type="button"
      :label="uploading ? t('imageField.uploading') : t('imageField.upload')"
      icon="pi pi-upload"
      severity="secondary"
      :loading="uploading"
      @click="pick"
    />
    <!-- Artist credit. Empty = no credit shown anywhere. The backend
         strips a leading ``@`` if pasted. -->
    <InputText v-model="artist" :placeholder="t('imageField.artistPlaceholder')" fluid />
  </section>
</template>

<style scoped>
.form-section { display: flex; flex-direction: column; gap: 0.75rem; }
.section-heading { margin: 0; font-size: 1.0625rem; font-weight: 600; }
.muted { color: var(--brand-text-muted); }
/* 4:5 portrait preview, capped so it doesn't dominate the form. */
.image-preview { display: flex; flex-direction: column; gap: 0.5rem; }
.image-preview img {
  width: 100%;
  max-width: 240px;
  aspect-ratio: 4 / 5;
  object-fit: cover;
  border-radius: 8px;
  border: 1px solid var(--brand-border);
}
.image-actions { display: flex; gap: 0.5rem; }
</style>
