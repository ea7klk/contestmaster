<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{ label: string; scrollStep?: number }>()
const region = ref<HTMLDivElement | null>(null)

function handleKeydown(event: KeyboardEvent) {
  const element = region.value
  if (!element) return
  const maxScroll = element.scrollWidth - element.clientWidth
  if (maxScroll <= 0) return

  let target: number | undefined
  switch (event.key) {
    case 'ArrowLeft':
      target = element.scrollLeft - (props.scrollStep ?? 160)
      break
    case 'ArrowRight':
      target = element.scrollLeft + (props.scrollStep ?? 160)
      break
    case 'Home':
      target = 0
      break
    case 'End':
      target = maxScroll
      break
    default:
      return
  }
  event.preventDefault()
  element.scrollLeft = Math.max(0, Math.min(maxScroll, target))
}
</script>

<template>
  <div
    ref="region"
    class="keyboard-scroll-region"
    role="region"
    tabindex="0"
    :aria-label="`${label}. Use the left and right arrow keys to scroll horizontally.`"
    aria-keyshortcuts="ArrowLeft ArrowRight Home End"
    @keydown="handleKeydown"
  >
    <slot />
  </div>
</template>
