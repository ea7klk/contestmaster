<script setup lang="ts">
import { computed, useId } from 'vue'

defineOptions({ name: 'ConditionEditor' })

const props = withDefaults(
  defineProps<{ modelValue?: Record<string, unknown>; depth?: number }>(),
  {
    modelValue: () => ({
      kind: 'compare',
      fact: 'qso.band',
      operator: 'eq',
      value: '20m',
    }),
    depth: 0,
  },
)
const emit = defineEmits<{
  'update:modelValue': [value: Record<string, unknown>]
}>()
const factsListId = useId()

type ConditionKind = 'compare' | 'all' | 'any' | 'not'
const kind = computed(
  () => (props.modelValue.kind as ConditionKind | undefined) ?? 'compare',
)
const valueKind = computed(() => {
  const value = props.modelValue.value
  if (Array.isArray(value)) return 'list'
  if (typeof value === 'number') return 'integer'
  if (typeof value === 'boolean') return 'boolean'
  return 'text'
})
const listValue = computed(() =>
  Array.isArray(props.modelValue.value)
    ? props.modelValue.value.map(String).join(', ')
    : '',
)
const childConditions = computed(() =>
  Array.isArray(props.modelValue.conditions)
    ? (props.modelValue.conditions as Record<string, unknown>[])
    : [],
)
const negatedCondition = computed(() =>
  props.modelValue.condition && typeof props.modelValue.condition === 'object'
    ? (props.modelValue.condition as Record<string, unknown>)
    : { kind: 'compare', fact: 'qso.band', operator: 'eq', value: '20m' },
)
const compareOperators = [
  'eq',
  'ne',
  'in',
  'not_in',
  'lt',
  'lte',
  'gt',
  'gte',
  'matches',
  'exists',
]

function update(patch: Record<string, unknown>) {
  emit('update:modelValue', { ...props.modelValue, ...patch })
}

function setKind(nextKind: ConditionKind) {
  if (nextKind === 'compare') {
    emit('update:modelValue', {
      kind: 'compare',
      fact: 'qso.band',
      operator: 'eq',
      value: '20m',
    })
  } else if (nextKind === 'not') {
    emit('update:modelValue', {
      kind: 'not',
      condition: {
        kind: 'compare',
        fact: 'qso.band',
        operator: 'eq',
        value: '20m',
      },
    })
  } else {
    emit('update:modelValue', {
      kind: nextKind,
      conditions: [
        { kind: 'compare', fact: 'qso.band', operator: 'eq', value: '20m' },
      ],
    })
  }
}

function updateValueKind(nextKind: string) {
  if (nextKind === 'list') update({ value: [] })
  else if (nextKind === 'integer') update({ value: 0 })
  else if (nextKind === 'boolean') update({ value: false })
  else update({ value: '' })
}

function updateOperator(operator: string) {
  const value = props.modelValue.value
  if (operator === 'in' || operator === 'not_in') {
    update({
      operator,
      value: Array.isArray(value) ? value : value == null ? [] : [value],
    })
  } else {
    update({
      operator,
      value: Array.isArray(value) ? (value[0] ?? '') : value,
    })
  }
}

function onValueInput(event: Event) {
  const value = (event.target as HTMLInputElement).value
  update({ value: valueKind.value === 'integer' ? Number(value) : value })
}

function onListInput(event: Event) {
  const values = (event.target as HTMLInputElement).value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
  update({ value: values })
}

function addCondition() {
  update({
    conditions: [
      ...childConditions.value,
      { kind: 'compare', fact: 'qso.band', operator: 'eq', value: '20m' },
    ],
  })
}

function removeCondition(index: number) {
  const conditions = childConditions.value
  if (conditions.length <= 1) return
  update({
    conditions: conditions.filter((_, childIndex) => childIndex !== index),
  })
}

function updateCondition(index: number, condition: Record<string, unknown>) {
  const conditions = [...childConditions.value]
  conditions[index] = condition
  update({ conditions })
}

function updateNegated(condition: Record<string, unknown>) {
  update({ condition })
}
</script>

<template>
  <fieldset class="condition-editor">
    <legend>Condition</legend>
    <label>
      Match type
      <select
        :value="kind"
        @change="
          setKind(($event.target as HTMLSelectElement).value as ConditionKind)
        "
      >
        <option value="compare">Compare a value</option>
        <option value="all">All conditions</option>
        <option value="any">Any condition</option>
        <option value="not">Not a condition</option>
      </select>
    </label>

    <template v-if="kind === 'compare'">
      <label>
        Fact path
        <input
          :value="modelValue.fact"
          :list="factsListId"
          maxlength="160"
          placeholder="qso.band"
          @input="update({ fact: ($event.target as HTMLInputElement).value })"
        />
      </label>
      <datalist :id="factsListId">
        <option value="qso.band" />
        <option value="qso.mode" />
        <option value="qso.continent" />
        <option value="qso.entity" />
        <option value="qso.cq_zone" />
        <option value="qso.itu_zone" />
        <option value="entry.categories.operator" />
        <option value="entry.declarations.license_class" />
        <option value="entry.declarations.membership" />
        <option value="station.callsign" />
      </datalist>
      <label>
        Comparison
        <select
          :value="modelValue.operator"
          @change="updateOperator(($event.target as HTMLSelectElement).value)"
        >
          <option
            v-for="operator in compareOperators"
            :key="operator"
            :value="operator"
          >
            {{ operator }}
          </option>
        </select>
      </label>
      <template v-if="modelValue.operator !== 'exists'">
        <label>
          Value type
          <select
            :value="valueKind"
            @change="
              updateValueKind(($event.target as HTMLSelectElement).value)
            "
          >
            <option value="text">Text</option>
            <option value="integer">Integer</option>
            <option value="boolean">Boolean</option>
            <option value="list">Text list</option>
          </select>
        </label>
        <label v-if="valueKind === 'boolean'" class="check-control">
          <input
            type="checkbox"
            :checked="Boolean(modelValue.value)"
            @change="
              update({ value: ($event.target as HTMLInputElement).checked })
            "
          />
          Value is true
        </label>
        <label v-else>
          {{
            valueKind === 'list' ? 'Comma-separated values' : 'Compare value'
          }}
          <input
            :type="valueKind === 'integer' ? 'number' : 'text'"
            :step="valueKind === 'integer' ? 1 : undefined"
            :value="valueKind === 'list' ? listValue : modelValue.value"
            @input="
              valueKind === 'list' ? onListInput($event) : onValueInput($event)
            "
          />
        </label>
      </template>
    </template>

    <div v-else-if="kind === 'not'" class="condition-child">
      <ConditionEditor
        :model-value="negatedCondition"
        :depth="depth + 1"
        @update:model-value="updateNegated"
      />
    </div>

    <div v-else class="condition-group">
      <p>
        {{
          kind === 'all'
            ? 'Every condition below must match.'
            : 'At least one condition below must match.'
        }}
      </p>
      <div
        v-for="(condition, index) in childConditions"
        :key="index"
        class="condition-child"
      >
        <ConditionEditor
          :model-value="condition"
          :depth="depth + 1"
          @update:model-value="updateCondition(index, $event)"
        />
        <button
          v-if="childConditions.length > 1"
          type="button"
          class="quiet-button"
          @click="removeCondition(index)"
        >
          Remove condition
        </button>
      </div>
      <button type="button" class="secondary-button" @click="addCondition">
        Add condition
      </button>
    </div>
  </fieldset>
</template>

<style scoped>
.condition-editor {
  display: grid;
  gap: 0.7rem;
  min-width: 0;
  margin: 0;
  padding: 0.9rem;
  border: 1px solid var(--color-border);
  border-radius: 0.6rem;
  background: var(--color-surface-muted);
}
legend {
  padding: 0 0.3rem;
  font-weight: 650;
}
label {
  display: grid;
  gap: 0.35rem;
  max-width: 40rem;
  color: var(--color-brand-900);
  font-size: 0.9rem;
  font-weight: 600;
}
input,
select {
  min-height: 2.55rem;
  padding: 0.5rem 0.65rem;
  border: 1px solid var(--color-border);
  border-radius: 0.45rem;
  color: var(--color-ink);
  background: var(--color-surface);
  font: inherit;
}
input[type='checkbox'] {
  width: 1.1rem;
  min-height: 1.1rem;
  accent-color: var(--color-brand-700);
}
.check-control {
  display: flex;
  align-items: center;
}
.condition-group > p {
  margin: 0.1rem 0 0.6rem;
  color: var(--color-muted);
}
.condition-child {
  margin: 0.7rem 0;
}
.secondary-button,
.quiet-button {
  min-height: 2.3rem;
  padding: 0.4rem 0.7rem;
  border: 1px solid var(--color-border-strong);
  border-radius: 0.45rem;
  color: var(--color-brand-900);
  background: var(--color-surface);
  font: inherit;
  cursor: pointer;
}
.quiet-button {
  margin-top: 0.5rem;
  color: var(--color-muted);
  font-size: 0.85rem;
}
</style>
