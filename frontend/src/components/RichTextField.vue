<script setup lang="ts">
import Bold from "@tiptap/extension-bold";
import Document from "@tiptap/extension-document";
import HardBreak from "@tiptap/extension-hard-break";
import History from "@tiptap/extension-history";
import Italic from "@tiptap/extension-italic";
import Link from "@tiptap/extension-link";
import Paragraph from "@tiptap/extension-paragraph";
import Placeholder from "@tiptap/extension-placeholder";
import Strike from "@tiptap/extension-strike";
import Text from "@tiptap/extension-text";
import Underline from "@tiptap/extension-underline";
import { Editor, EditorContent } from "@tiptap/vue-3";
import { onBeforeUnmount, onMounted, shallowRef, watch } from "vue";
import { useI18n } from "vue-i18n";

// A minimal rich-text editor for the "details" body. Its schema is
// deliberately constrained to exactly the marks the server sanitizer
// allows (bold / italic / underline / strikethrough / link, plus
// paragraphs and hard breaks), so what an organiser sees is exactly
// what gets stored — nothing the editor can produce is later stripped.
const props = defineProps<{ modelValue: string; placeholder?: string }>();
const emit = defineEmits<{ "update:modelValue": [string] }>();

const { t } = useI18n();
const editor = shallowRef<Editor>();

onMounted(() => {
  editor.value = new Editor({
    content: props.modelValue || "",
    extensions: [
      Document,
      Paragraph,
      Text,
      HardBreak,
      History,
      Bold,
      Italic,
      Underline,
      Strike,
      Link.configure({
        openOnClick: false,
        autolink: true,
        protocols: ["http", "https", "mailto"],
        HTMLAttributes: { rel: "nofollow noopener noreferrer" },
      }),
      Placeholder.configure({ placeholder: () => props.placeholder ?? "" }),
    ],
    onUpdate: ({ editor: e }) => {
      // Emit "" for an effectively-empty doc so the parent's
      // ``|| null`` collapses it, rather than storing "<p></p>".
      emit("update:modelValue", e.isEmpty ? "" : e.getHTML());
    },
  });
});

onBeforeUnmount(() => editor.value?.destroy());

// Sync when the parent replaces the value out from under us (e.g. an
// edit page that loads the existing entity after mount). Skip while the
// user is typing so the caret never jumps.
watch(
  () => props.modelValue,
  (val) => {
    const e = editor.value;
    if (!e || e.isFocused) return;
    const current = e.isEmpty ? "" : e.getHTML();
    if (val !== current) e.commands.setContent(val || "");
  },
);

function toggle(mark: "bold" | "italic" | "underline" | "strike"): void {
  const e = editor.value;
  if (!e) return;
  const chain = e.chain().focus();
  ({
    bold: () => chain.toggleBold().run(),
    italic: () => chain.toggleItalic().run(),
    underline: () => chain.toggleUnderline().run(),
    strike: () => chain.toggleStrike().run(),
  })[mark]();
}

function setLink(): void {
  const e = editor.value;
  if (!e) return;
  const prev = e.getAttributes("link").href as string | undefined;
  const url = window.prompt(t("richtext.linkPrompt"), prev ?? "https://");
  if (url === null) return; // cancelled
  if (url.trim() === "") {
    e.chain().focus().extendMarkRange("link").unsetLink().run();
    return;
  }
  e.chain().focus().extendMarkRange("link").setLink({ href: url.trim() }).run();
}
</script>

<template>
  <div class="rt">
    <div v-if="editor" class="rt-toolbar">
      <button
        type="button"
        class="rt-btn"
        :class="{ active: editor.isActive('bold') }"
        :title="t('richtext.bold')"
        :aria-label="t('richtext.bold')"
        @click="toggle('bold')"
      >
        <strong>B</strong>
      </button>
      <button
        type="button"
        class="rt-btn"
        :class="{ active: editor.isActive('italic') }"
        :title="t('richtext.italic')"
        :aria-label="t('richtext.italic')"
        @click="toggle('italic')"
      >
        <em>I</em>
      </button>
      <button
        type="button"
        class="rt-btn"
        :class="{ active: editor.isActive('underline') }"
        :title="t('richtext.underline')"
        :aria-label="t('richtext.underline')"
        @click="toggle('underline')"
      >
        <span style="text-decoration: underline">U</span>
      </button>
      <button
        type="button"
        class="rt-btn"
        :class="{ active: editor.isActive('strike') }"
        :title="t('richtext.strike')"
        :aria-label="t('richtext.strike')"
        @click="toggle('strike')"
      >
        <span style="text-decoration: line-through">S</span>
      </button>
      <button
        type="button"
        class="rt-btn"
        :class="{ active: editor.isActive('link') }"
        :title="t('richtext.link')"
        :aria-label="t('richtext.link')"
        @click="setLink"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
          <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
        </svg>
      </button>
    </div>
    <EditorContent :editor="editor" class="rt-content" />
  </div>
</template>

<style scoped>
.rt {
  border: 1px solid var(--brand-border);
  border-radius: 8px;
  background: var(--brand-surface);
  overflow: hidden;
}
.rt-toolbar {
  display: flex;
  gap: 0.125rem;
  padding: 0.25rem;
  border-bottom: 1px solid var(--brand-border);
  background: color-mix(in srgb, var(--brand-surface) 92%, var(--brand-border));
}
.rt-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--brand-text);
  cursor: pointer;
  font-size: 0.95rem;
  line-height: 1;
}
.rt-btn:hover {
  background: color-mix(in srgb, var(--brand-border) 60%, transparent);
}
.rt-btn.active {
  background: var(--brand-red);
  color: #fff;
}
.rt-content :deep(.ProseMirror) {
  min-height: 5.5rem;
  padding: 0.625rem 0.75rem;
  outline: none;
  line-height: 1.5;
}
.rt-content :deep(.ProseMirror p) {
  margin: 0 0 0.5rem;
}
.rt-content :deep(.ProseMirror p:last-child) {
  margin-bottom: 0;
}
.rt-content :deep(.ProseMirror a) {
  color: var(--brand-red);
  text-decoration: underline;
}
/* Placeholder shown on an empty first paragraph. */
.rt-content :deep(.ProseMirror p.is-editor-empty:first-child::before) {
  content: attr(data-placeholder);
  float: left;
  height: 0;
  color: var(--brand-text-muted);
  pointer-events: none;
}
</style>
