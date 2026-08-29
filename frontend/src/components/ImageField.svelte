<script lang="ts">
import AppButton from "@/components/AppButton.svelte";
import AppInput from "@/components/AppInput.svelte";
import { t } from "@/i18n.svelte";
import { ApiError } from "@/api/client";
import { useImageUpload } from "@/composables/useImageUpload.svelte";
import { untrack } from "svelte";

import { useToasts } from "@/lib/toasts";

/** Shared hero-image block for the organiser edit pages (events,
 *  forms, datepolls): a 4:5 preview with upload / replace / remove,
 *  plus the optional artist-credit handle.
 *
 *  In **edit mode** (the row exists) a pick uploads immediately. In
 *  **create mode** (no id yet) the file is held client-side with a
 *  local preview; the parent calls ``flushPendingUpload(newId)`` right
 *  after the create succeeds, so the organiser never has to "save
 *  first". ``imageUrl`` is display-only (the upload endpoint persists
 *  it); ``artist`` feeds the create/update payload. */
let {
  resource,
  entityId,
  imageUrl = $bindable(),
  artist = $bindable(),
}: {
  resource: string;
  entityId: string | null;
  imageUrl: string | null;
  artist: string | null;
} = $props();

const toasts = useToasts();
// The resource a field is for is fixed for its lifetime.
const images = useImageUpload(untrack(() => resource));

let uploading = $state(false);
let fileInput = $state<HTMLInputElement | null>(null);

// Create-mode hold: the picked file isn't uploaded until the row
// exists. ``previewUrl`` is a local object URL for the preview.
let pendingFile = $state<File | null>(null);
let previewUrl = $state<string | null>(null);

function setPreview(file: File | null): void {
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = file ? URL.createObjectURL(file) : null;
}

$effect(() => () => {
  if (previewUrl) URL.revokeObjectURL(previewUrl);
});

function pick(): void {
  fileInput?.click();
}

function describeError(err: unknown): string {
  if (err instanceof ApiError) return `${err.status} ${err.message}`;
  if (err instanceof Error && err.message) return err.message;
  return "unknown";
}

async function onSelected(ev: Event): Promise<void> {
  const input = ev.currentTarget as HTMLInputElement;
  const file = input.files?.[0];
  input.value = ""; // allow re-picking the same file
  if (!file) return;
  if (!entityId) {
    // Create mode: hold the file and show a local preview. Uploaded by
    // ``flushPendingUpload`` once the parent has created the row.
    pendingFile = file;
    setPreview(file);
    return;
  }
  uploading = true;
  try {
    const updated = await images.upload(entityId, file);
    imageUrl = updated.image_url;
    toasts.success(t("imageField.uploaded"));
  } catch (err) {
    toasts.error(`${t("imageField.uploadFailed")}: ${describeError(err)}`);
  } finally {
    uploading = false;
  }
}

async function removeImage(): Promise<void> {
  if (pendingFile) {
    // Not uploaded yet, so just drop the held file.
    pendingFile = null;
    setPreview(null);
    return;
  }
  if (!entityId) return;
  uploading = true;
  try {
    const updated = await images.remove(entityId);
    imageUrl = updated.image_url;
  } catch (err) {
    toasts.error(`${t("imageField.removeFailed")}: ${describeError(err)}`);
  } finally {
    uploading = false;
  }
}

/** Upload a create-mode held file to the freshly created row. Called by
 *  the parent's submit handler after the create succeeds; a no-op if
 *  nothing is pending. Failures surface a toast but don't block the
 *  parent's navigation: the row is already saved, just without its
 *  image. */
export async function flushPendingUpload(id: string): Promise<void> {
  if (!pendingFile) return;
  try {
    const updated = await images.upload(id, pendingFile);
    imageUrl = updated.image_url;
  } catch (err) {
    toasts.error(`${t("imageField.uploadFailed")}: ${describeError(err)}`);
  } finally {
    pendingFile = null;
    setPreview(null);
  }
}
</script>

<section class="form-section">
  <h2 class="section-heading">{t("imageField.heading")}</h2>
  <input
    bind:this={fileInput}
    type="file"
    accept="image/jpeg,image/png,image/webp"
    style="display: none"
    onchange={onSelected}
  />
  {#if imageUrl || previewUrl}
    <div class="image-preview">
      <img src={imageUrl ?? previewUrl ?? ""} alt={t("imageField.alt")} />
      <div class="image-actions">
        <AppButton
          type="button"
          label={t("imageField.replace")}
          icon="refresh"
          size="small"
          severity="secondary"
          disabled={uploading}
          onclick={pick}
        />
        <AppButton
          type="button"
          label={t("imageField.remove")}
          icon="trash"
          size="small"
          severity="secondary"
          text
          disabled={uploading}
          onclick={removeImage}
        />
      </div>
    </div>
  {:else}
    <AppButton
      type="button"
      label={uploading ? t("imageField.uploading") : t("imageField.upload")}
      icon="upload"
      severity="secondary"
      loading={uploading}
      onclick={pick}
    />
  {/if}
  <!-- Artist credit. Empty means no credit shown anywhere. The backend
       strips a leading ``@`` if pasted. -->
  <AppInput bind:value={artist} placeholder={t("imageField.artistPlaceholder")} fluid />
</section>

<style>
.form-section { display: flex; flex-direction: column; gap: 0.75rem; }
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
