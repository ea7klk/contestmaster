<script setup lang="ts">
/* global HTMLElement */
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    open: boolean
    title: string
    description: string
    confirmLabel: string
    requiredText?: string
    requiredTextLabel?: string
    auditReasonLabel?: string
    busy?: boolean
    confirmVariant?: 'danger' | 'primary'
  }>(),
  {
    requiredText: '',
    requiredTextLabel: '',
    auditReasonLabel: '',
    busy: false,
    confirmVariant: 'danger',
  },
)

const emit = defineEmits<{
  confirm: [value: { confirmationText: string; auditReason: string }]
  cancel: []
}>()

const dialog = ref<HTMLElement | null>(null)
const confirmationText = ref('')
const auditReason = ref('')
let previousFocus: HTMLElement | null = null
const confirmationMatches = computed(
  () => !props.requiredText || confirmationText.value === props.requiredText,
)
const canConfirm = computed(() => !props.busy && confirmationMatches.value)

function trapFocus(event: KeyboardEvent) {
  if (!props.open) return
  if (event.key === 'Escape') {
    event.preventDefault()
    cancel()
    return
  }
  if (event.key !== 'Tab' || !dialog.value) return
  const controls = Array.from(
    dialog.value.querySelectorAll<HTMLElement>(
      'button:not(:disabled), input:not(:disabled), textarea:not(:disabled)',
    ),
  )
  if (!controls.length) {
    event.preventDefault()
    dialog.value.focus()
    return
  }
  const first = controls[0]!
  const last = controls[controls.length - 1]!
  if (!dialog.value.contains(document.activeElement)) {
    event.preventDefault()
    ;(event.shiftKey ? last : first).focus()
  } else if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

watch(
  () => props.open,
  async (open) => {
    if (open) {
      document.addEventListener('keydown', trapFocus, true)
      previousFocus =
        document.activeElement instanceof HTMLElement
          ? document.activeElement
          : null
      confirmationText.value = ''
      auditReason.value = ''
      await nextTick()
      const initialFocus = props.requiredText
        ? dialog.value?.querySelector<HTMLInputElement>(
            '[data-confirmation-input]',
          )
        : dialog.value?.querySelector<HTMLButtonElement>('[data-cancel-button]')
      initialFocus?.focus()
    } else {
      document.removeEventListener('keydown', trapFocus, true)
      previousFocus?.focus()
      previousFocus = null
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => document.removeEventListener('keydown', trapFocus, true))

function cancel() {
  if (!props.busy) emit('cancel')
}

function confirm() {
  if (!canConfirm.value) return
  emit('confirm', {
    confirmationText: confirmationText.value,
    auditReason: auditReason.value.trim(),
  })
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="confirmation-modal-backdrop" @click.self="cancel">
      <section
        ref="dialog"
        class="confirmation-modal"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirmation-modal-title"
        aria-describedby="confirmation-modal-description"
        tabindex="-1"
      >
        <h2 id="confirmation-modal-title">{{ title }}</h2>
        <p id="confirmation-modal-description">{{ description }}</p>
        <form @submit.prevent="confirm">
          <label v-if="requiredText" class="confirmation-modal-field">
            {{ requiredTextLabel }}
            <input
              v-model="confirmationText"
              data-confirmation-input
              autocomplete="off"
              :disabled="busy"
              :aria-invalid="Boolean(confirmationText) && !confirmationMatches"
            />
          </label>
          <label v-if="auditReasonLabel" class="confirmation-modal-field">
            {{ auditReasonLabel }}
            <textarea v-model="auditReason" rows="3" :disabled="busy" />
          </label>
          <div class="confirmation-modal-actions">
            <button
              type="button"
              class="secondary-button"
              data-cancel-button
              :disabled="busy"
              @click="cancel"
            >
              {{ $tr('Cancel') }}
            </button>
            <button
              type="submit"
              :class="
                confirmVariant === 'primary'
                  ? 'primary-button'
                  : 'danger-button'
              "
              :disabled="!canConfirm"
            >
              {{ confirmLabel }}
            </button>
          </div>
        </form>
      </section>
    </div>
  </Teleport>
</template>
