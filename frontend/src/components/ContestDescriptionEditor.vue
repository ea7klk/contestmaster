<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { EditorContent, useEditor } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import { Markdown } from '@tiptap/markdown'
import { TableKit } from '@tiptap/extension-table'
import { renderContestMarkdown } from '../views/contestMarkdown'

const props = defineProps<{ modelValue: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const maximumMarkdownLength = 10_000
const markdownTooLong = ref(false)
const linkUrl = ref('')
const lastValidMarkdown = ref(props.modelValue)
const previewHtml = computed(() => renderContestMarkdown(props.modelValue))

const editor = useEditor({
  extensions: [
    StarterKit.configure({
      heading: { levels: [2, 3, 4] },
      link: { openOnClick: false },
    }),
    TableKit.configure({ table: { resizable: false } }),
    Markdown.configure({ markedOptions: { gfm: true } }),
  ],
  content: props.modelValue,
  contentType: 'markdown',
  editorProps: {
    attributes: {
      'aria-labelledby': 'contest-description-label',
      'aria-describedby': 'contest-description-help',
    },
  },
  onUpdate: ({ editor: currentEditor }) => {
    const markdown = currentEditor.getMarkdown()
    if (markdown.length > maximumMarkdownLength) {
      markdownTooLong.value = true
      currentEditor.commands.setContent(lastValidMarkdown.value, {
        contentType: 'markdown',
        emitUpdate: false,
      })
      return
    }
    markdownTooLong.value = false
    lastValidMarkdown.value = markdown
    emit('update:modelValue', markdown)
  },
})

watch(
  () => [editor.value, props.modelValue] as const,
  ([currentEditor, markdown]) => {
    if (currentEditor && currentEditor.getMarkdown() !== markdown) {
      currentEditor.commands.setContent(markdown, {
        contentType: 'markdown',
        emitUpdate: false,
      })
    }
    lastValidMarkdown.value = markdown
  },
)

function toggleMark(mark: 'bold' | 'italic') {
  const currentEditor = editor.value
  if (!currentEditor) return
  const chain = currentEditor.chain().focus()
  if (mark === 'bold') chain.toggleBold().run()
  else chain.toggleItalic().run()
}

function toggleHeading(level: 2 | 3) {
  editor.value?.chain().focus().toggleHeading({ level }).run()
}

function toggleList(type: 'bulletList' | 'orderedList') {
  const chain = editor.value?.chain().focus()
  if (type === 'bulletList') chain?.toggleBulletList().run()
  else chain?.toggleOrderedList().run()
}

function toggleBlockquote() {
  editor.value?.chain().focus().toggleBlockquote().run()
}

function applyLink() {
  const currentEditor = editor.value
  if (!currentEditor) return
  const href = linkUrl.value.trim()
  if (!href) return
  try {
    const parsed = new URL(href)
    if (!['http:', 'https:', 'mailto:'].includes(parsed.protocol)) return
  } catch {
    return
  }
  currentEditor.chain().focus().extendMarkRange('link').setLink({ href }).run()
}

function removeLink() {
  editor.value?.chain().focus().extendMarkRange('link').unsetLink().run()
  linkUrl.value = ''
}
</script>

<template>
  <div class="contest-description-editor">
    <div
      class="rich-text-toolbar"
      role="toolbar"
      :aria-label="$tr('Description formatting')"
    >
      <button
        type="button"
        :aria-label="$tr('Bold')"
        :aria-pressed="Boolean(editor?.isActive('bold'))"
        :disabled="!editor"
        @click="toggleMark('bold')"
      >
        <strong>B</strong>
      </button>
      <button
        type="button"
        :aria-label="$tr('Italic')"
        :aria-pressed="Boolean(editor?.isActive('italic'))"
        :disabled="!editor"
        @click="toggleMark('italic')"
      >
        <em>I</em>
      </button>
      <button
        type="button"
        :aria-label="$tr('Heading level 2')"
        :aria-pressed="Boolean(editor?.isActive('heading', { level: 2 }))"
        :disabled="!editor"
        @click="toggleHeading(2)"
      >
        H2
      </button>
      <button
        type="button"
        :aria-label="$tr('Heading level 3')"
        :aria-pressed="Boolean(editor?.isActive('heading', { level: 3 }))"
        :disabled="!editor"
        @click="toggleHeading(3)"
      >
        H3
      </button>
      <button
        type="button"
        :aria-label="$tr('Bulleted list')"
        :aria-pressed="Boolean(editor?.isActive('bulletList'))"
        :disabled="!editor"
        @click="toggleList('bulletList')"
      >
        • {{ $tr('Bulleted list') }}
      </button>
      <button
        type="button"
        :aria-label="$tr('Numbered list')"
        :aria-pressed="Boolean(editor?.isActive('orderedList'))"
        :disabled="!editor"
        @click="toggleList('orderedList')"
      >
        1. {{ $tr('Numbered list') }}
      </button>
      <button
        type="button"
        :aria-label="$tr('Quote')"
        :aria-pressed="Boolean(editor?.isActive('blockquote'))"
        :disabled="!editor"
        @click="toggleBlockquote"
      >
        “ ”
      </button>
      <label class="link-editor">
        {{ $tr('Link URL') }}
        <input
          v-model="linkUrl"
          type="url"
          placeholder="https://example.org/rules"
          :disabled="!editor"
        />
      </label>
      <button type="button" :disabled="!editor" @click="applyLink">
        {{ $tr('Apply link') }}
      </button>
      <button type="button" :disabled="!editor" @click="removeLink">
        {{ $tr('Remove link') }}
      </button>
    </div>
    <EditorContent :editor="editor" class="rich-text-surface" />
    <p v-if="markdownTooLong" class="editor-length-error" role="alert">
      {{ $tr('Contest description is limited to 10,000 Markdown characters.') }}
    </p>
    <section
      class="description-preview"
      aria-labelledby="description-preview-title"
    >
      <h2 id="description-preview-title">{{ $tr('Preview') }}</h2>
      <div v-if="previewHtml" class="preview-content" v-html="previewHtml" />
      <p v-else class="preview-empty">{{ $tr('Nothing to preview yet.') }}</p>
    </section>
  </div>
</template>

<style scoped>
.contest-description-editor {
  display: grid;
  gap: 0.6rem;
  min-width: 0;
}

.rich-text-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: 0.4rem;
}

.rich-text-toolbar button {
  min-height: 2.5rem;
  padding: 0.4rem 0.65rem;
  border: 1px solid var(--color-border-strong);
  border-radius: 0.35rem;
  color: var(--color-brand-900);
  background: var(--color-surface);
  cursor: pointer;
}

.rich-text-toolbar button[aria-pressed='true'] {
  color: var(--color-on-brand);
  background: var(--color-brand-800);
}

.rich-text-toolbar button:disabled {
  cursor: not-allowed;
  opacity: 0.65;
}

.link-editor {
  display: grid;
  gap: 0.2rem;
  min-width: min(100%, 14rem);
  flex: 1 1 14rem;
}

.rich-text-surface {
  min-height: 12rem;
  padding: 0.8rem;
  border: 1px solid var(--color-border-strong);
  border-radius: 0.4rem;
  background: var(--color-surface);
}

:deep(.tiptap) {
  min-height: 10rem;
  outline: none;
  line-height: 1.55;
}

:deep(.tiptap > :first-child),
.preview-content :deep(> :first-child) {
  margin-top: 0;
}

.description-preview {
  min-width: 0;
  padding: 0.8rem;
  border: 1px solid var(--color-border);
  border-radius: 0.4rem;
  background: var(--color-surface-muted);
}

.description-preview h2 {
  margin: 0 0 0.6rem;
  color: var(--color-brand-900);
  font-size: 1rem;
}

.preview-content {
  overflow-wrap: anywhere;
}

.preview-empty,
.editor-length-error {
  margin: 0;
  color: var(--color-muted);
}

.editor-length-error {
  color: var(--color-danger-700);
}
</style>
