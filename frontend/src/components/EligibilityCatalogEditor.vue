<script setup lang="ts">
import { computed } from 'vue'
import type { OperatingCatalogItem } from '../api/operatingCatalog'

const props = defineProps<{
  kind: 'band' | 'mode'
  items: OperatingCatalogItem[]
  selected: string[]
}>()
const emit = defineEmits<{ 'update:selected': [values: string[]] }>()

const displayItems = computed(() =>
  props.items.map((item) => ({
    ...item,
    frequency_range: item.kind === 'band' ? item.frequency_range : null,
    contest_free: item.kind === 'band' && item.contest_free,
  })),
)

function toggle(key: string, checked: boolean, selected: string[]) {
  const values = checked
    ? [...selected, key]
    : selected.filter((value) => value !== key)
  emit('update:selected', values)
}
</script>

<template>
  <fieldset class="eligibility-catalog">
    <legend>{{ kind === 'band' ? 'Eligible bands' : 'Allowed modes' }}</legend>
    <p v-if="kind === 'band'" class="schema-description">
      {{
        $tr(
          'Select the catalog bands accepted by this contest. A band marked no-contest is highlighted in red from the shared administrator-managed catalog. This advisory does not automatically exclude the band; the contest’s published rules remain authoritative.',
        )
      }}
    </p>
    <p v-else class="schema-description">
      {{
        $tr(
          'Select the operating modes accepted by this contest. Leave all unchecked to allow every mode. The contest’s published rules remain authoritative.',
        )
      }}
    </p>
    <p v-if="items.length === 0" role="status">
      {{ $tr('No active') }} {{ kind }} {{ $tr('values are configured.') }}
    </p>
    <div class="eligibility-options">
      <label
        v-for="item in displayItems"
        :key="item.key"
        :class="{ 'contest-free-band': kind === 'band' && item.contest_free }"
      >
        <input
          type="checkbox"
          :checked="selected.includes(item.key)"
          @change="
            toggle(
              item.key,
              ($event.target as HTMLInputElement).checked,
              selected,
            )
          "
        />
        <span>
          {{ item.label
          }}<template v-if="item.frequency_range">
            · {{ item.frequency_range }}</template
          >
          <strong
            v-if="kind === 'band' && item.contest_free"
            class="contest-free-label"
          >
            {{ $tr('No-contest band (advisory)') }}</strong
          >
          <small v-if="item.description">{{ item.description }}</small>
        </span>
      </label>
    </div>
  </fieldset>
</template>

<style scoped>
.eligibility-catalog {
  margin: 0.8rem 0;
  padding: 0.8rem;
  border: 1px solid var(--color-border);
  border-radius: 0.55rem;
}
.eligibility-options {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
  gap: 0.45rem;
}
.eligibility-options label {
  display: flex;
  align-items: flex-start;
  gap: 0.45rem;
  padding: 0.45rem;
  border-radius: 0.35rem;
}
.eligibility-options input {
  width: 1.1rem;
  min-height: 1.1rem;
  margin-top: 0.15rem;
  accent-color: var(--color-brand-700);
}
.eligibility-options small {
  display: block;
  color: var(--color-muted);
}
.contest-free-band {
  color: var(--color-error-ink);
  background: var(--color-error-surface);
  outline: 1px solid var(--color-error-ink);
}
.contest-free-label {
  font-size: 0.75rem;
}
</style>
