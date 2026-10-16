<script setup lang="ts">
import { computed } from 'vue'
import type { JsonSchema } from '../api/rulesets'

defineOptions({ name: 'RuleSchemaEditor' })

const props = withDefaults(
  defineProps<{
    schema: JsonSchema
    rootSchema: JsonSchema
    modelValue: unknown
    label?: string
    path?: string
    depth?: number
    hiddenProperties?: string[]
  }>(),
  { label: '', path: '', depth: 0, hiddenProperties: () => [] },
)

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

function resolveSchema(input: JsonSchema): JsonSchema {
  if (input.$ref) {
    const name = input.$ref.split('/').at(-1) ?? ''
    return props.rootSchema.$defs?.[name] ?? input
  }
  if (input.anyOf) {
    const options = input.anyOf.filter((option) => option.type !== 'null')
    const value = props.modelValue
    const selected = options.find((option) => {
      const type = typeof option.type === 'string' ? option.type : undefined
      if (type === 'string') return typeof value === 'string'
      if (type === 'integer' || type === 'number')
        return typeof value === 'number'
      if (type === 'boolean') return typeof value === 'boolean'
      if (type === 'array') return Array.isArray(value)
      if (type === 'object')
        return (
          value !== null && typeof value === 'object' && !Array.isArray(value)
        )
      return false
    })
    return selected ?? options[0] ?? input
  }
  return input
}

const effectiveSchema = computed(() => resolveSchema(props.schema))
const fieldLabel = computed(
  () => props.label || effectiveSchema.value.title || 'Value',
)
const isObject = computed(() => effectiveSchema.value.type === 'object')
const isArray = computed(() => effectiveSchema.value.type === 'array')
const isMap = computed(
  () =>
    isObject.value &&
    !effectiveSchema.value.properties &&
    Boolean(
      effectiveSchema.value.additionalProperties ||
      effectiveSchema.value.patternProperties,
    ),
)
const mapValueSchema = computed(() => {
  const patternSchema = Object.values(
    effectiveSchema.value.patternProperties ?? {},
  )[0]
  if (patternSchema) return patternSchema
  return typeof effectiveSchema.value.additionalProperties === 'object'
    ? effectiveSchema.value.additionalProperties
    : {}
})
const unionTypeOptions = computed(() => {
  const types = (props.schema.anyOf ?? [])
    .filter((option) => option.type !== 'null')
    .map((option) => resolveSchema(option))
    .map((option) =>
      Array.isArray(option.type) ? option.type[0] : option.type,
    )
    .filter((type): type is string =>
      ['string', 'integer', 'number', 'boolean', 'array'].includes(type ?? ''),
    )
  return [...new Set(types)]
})
const hasUnionTypeSelector = computed(() => unionTypeOptions.value.length > 1)
const isRequired = (key: string) =>
  effectiveSchema.value.required?.includes(key) ?? false
function isBooleanField(schema: JsonSchema): boolean {
  const resolved = resolveSchema(schema)
  if (resolved.anyOf) {
    const nonNullOptions = resolved.anyOf.filter(
      (option) => option.type !== 'null',
    )
    return (
      nonNullOptions.length === 1 && isBooleanField(nonNullOptions[0] ?? {})
    )
  }
  const type = resolved.type
  return (
    type === 'boolean' ||
    (Array.isArray(type) &&
      type.includes('boolean') &&
      type.every((item) => item === 'boolean' || item === 'null'))
  )
}
const objectValue = computed(() =>
  props.modelValue &&
  typeof props.modelValue === 'object' &&
  !Array.isArray(props.modelValue)
    ? (props.modelValue as Record<string, unknown>)
    : {},
)
const arrayValue = computed(() =>
  Array.isArray(props.modelValue) ? props.modelValue : [],
)
const primitiveSchema = computed(() => {
  if (Array.isArray(effectiveSchema.value.type)) {
    return {
      ...effectiveSchema.value,
      type: effectiveSchema.value.type.find((type) => type !== 'null'),
    }
  }
  return effectiveSchema.value
})
const primitiveType = computed(() => primitiveSchema.value.type ?? 'string')
const enumOptions = computed(() => primitiveSchema.value.enum ?? [])
const inputValue = computed(() =>
  props.modelValue == null ? '' : String(props.modelValue),
)

function initialValue(schema: JsonSchema): unknown {
  if (schema.default !== undefined) return schema.default
  const resolved = resolveSchema(schema)
  if (resolved.const !== undefined) return resolved.const
  if (resolved.default !== undefined) return resolved.default
  if (resolved.enum?.length) return resolved.enum[0]
  if (resolved.type === 'object') {
    const value: Record<string, unknown> = {}
    for (const [key, childSchema] of Object.entries(
      resolved.properties ?? {},
    )) {
      if (
        resolved.required?.includes(key) ||
        childSchema.default !== undefined
      ) {
        value[key] = initialValue(childSchema)
      }
    }
    return value
  }
  if (resolved.type === 'array') return []
  if (resolved.type === 'boolean') return false
  if (resolved.type === 'integer' || resolved.type === 'number')
    return resolved.minimum ?? 0
  return ''
}

function setValue(value: unknown) {
  emit('update:modelValue', value)
}

function updateProperty(key: string, value: unknown) {
  setValue({ ...objectValue.value, [key]: value })
}

function removeProperty(key: string) {
  const next = { ...objectValue.value }
  delete next[key]
  setValue(next)
}

function toggleProperty(key: string, schema: JsonSchema, enabled: boolean) {
  if (enabled) updateProperty(key, initialValue(schema))
  else removeProperty(key)
}

function updateArrayItem(index: number, value: unknown) {
  const next = [...arrayValue.value]
  next[index] = value
  setValue(next)
}

function addArrayItem() {
  if (arrayValue.value.length >= (effectiveSchema.value.maxItems ?? 500)) return
  setValue([
    ...arrayValue.value,
    initialValue(effectiveSchema.value.items ?? {}),
  ])
}

function removeArrayItem(index: number) {
  setValue(arrayValue.value.filter((_, itemIndex) => itemIndex !== index))
}

function mapRows() {
  return Object.entries(objectValue.value)
}

function addMapRow() {
  const values = objectValue.value
  let key = 'value'
  let suffix = 2
  while (Object.hasOwn(values, key)) {
    key = `value-${suffix}`
    suffix += 1
  }
  setValue({ ...values, [key]: initialValue(mapValueSchema.value) })
}

function selectUnionType(type: string) {
  const option = (props.schema.anyOf ?? [])
    .filter((candidate) => candidate.type !== 'null')
    .map((candidate) => resolveSchema(candidate))
    .find((candidate) => candidate.type === type)
  if (option) setValue(initialValue(option))
}

function renameMapKey(oldKey: string, newKey: string) {
  if (
    !newKey.trim() ||
    (newKey !== oldKey && Object.hasOwn(objectValue.value, newKey))
  )
    return
  const next: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(objectValue.value)) {
    next[key === oldKey ? newKey : key] = value
  }
  setValue(next)
}

function updateMapValue(key: string, value: unknown) {
  setValue({ ...objectValue.value, [key]: value })
}

function onPrimitiveInput(event: Event) {
  const target = event.target as HTMLInputElement | HTMLTextAreaElement
  if (primitiveType.value === 'integer') {
    if (!/^-?[0-9]+$/.test(target.value)) return
    setValue(Number(target.value))
  } else if (primitiveType.value === 'number') {
    if (!/^-?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)$/.test(target.value)) return
    setValue(Number(target.value))
  } else {
    setValue(target.value)
  }
}

function onBooleanInput(event: Event) {
  setValue((event.target as HTMLInputElement).checked)
}

function onEnumInput(event: Event) {
  const value = (event.target as HTMLSelectElement).value
  const option = enumOptions.value.find((item) => String(item) === value)
  setValue(option)
}
</script>

<template>
  <fieldset
    class="schema-editor"
    :class="{ 'schema-editor-nested': depth > 0 }"
  >
    <legend v-if="label || effectiveSchema.title">{{ fieldLabel }}</legend>

    <template v-if="isObject && !isMap">
      <template
        v-for="(childSchema, key) in effectiveSchema.properties"
        :key="key"
      >
        <div
          v-if="key !== 'eligible_if' && !hiddenProperties.includes(key)"
          class="schema-field"
        >
          <template v-if="isBooleanField(childSchema)">
            <label class="schema-boolean">
              <input
                type="checkbox"
                :checked="
                  Boolean(objectValue[key] ?? initialValue(childSchema))
                "
                @change="
                  updateProperty(
                    key,
                    ($event.target as HTMLInputElement).checked,
                  )
                "
              />
              {{ childSchema.title || key.replaceAll('_', ' ') }}
            </label>
            <p v-if="childSchema.description" class="schema-description">
              {{ childSchema.description }}
            </p>
          </template>
          <template v-else>
            <label v-if="!isRequired(key)" class="schema-enable">
              <input
                type="checkbox"
                :checked="Object.hasOwn(objectValue, key)"
                @change="
                  toggleProperty(
                    key,
                    childSchema,
                    ($event.target as HTMLInputElement).checked,
                  )
                "
              />
              Configure {{ childSchema.title || key.replaceAll('_', ' ') }}
            </label>
            <RuleSchemaEditor
              v-if="isRequired(key) || Object.hasOwn(objectValue, key)"
              :schema="childSchema"
              :root-schema="rootSchema"
              :model-value="objectValue[key] ?? initialValue(childSchema)"
              :label="
                key === 'kind'
                  ? ''
                  : childSchema.title || key.replaceAll('_', ' ')
              "
              :path="`${path}-${key}`"
              :depth="depth + 1"
              :hidden-properties="hiddenProperties"
              @update:model-value="updateProperty(key, $event)"
            />
          </template>
        </div>
      </template>
    </template>

    <template v-else-if="isArray">
      <p v-if="effectiveSchema.description" class="schema-description">
        {{ effectiveSchema.description }}
      </p>
      <div
        v-for="(item, index) in arrayValue"
        :key="index"
        class="schema-array-item"
      >
        <RuleSchemaEditor
          :schema="effectiveSchema.items ?? {}"
          :root-schema="rootSchema"
          :model-value="item"
          :label="`${fieldLabel} ${index + 1}`"
          :path="`${path}-${index}`"
          :depth="depth + 1"
          @update:model-value="updateArrayItem(index, $event)"
        />
        <button
          type="button"
          class="quiet-button"
          @click="removeArrayItem(index)"
        >
          Remove
        </button>
      </div>
      <button
        type="button"
        class="secondary-button"
        :disabled="arrayValue.length >= (effectiveSchema.maxItems ?? 500)"
        @click="addArrayItem"
      >
        Add {{ fieldLabel.toLowerCase() }}
      </button>
    </template>

    <template v-else-if="isMap">
      <p v-if="effectiveSchema.description" class="schema-description">
        {{ effectiveSchema.description }}
      </p>
      <div
        v-for="([key, value], index) in mapRows()"
        :key="key"
        class="schema-map-row"
      >
        <label :for="`${path}-${index}-key`">Key</label>
        <input
          :id="`${path}-${index}-key`"
          :value="key"
          autocomplete="off"
          @change="renameMapKey(key, ($event.target as HTMLInputElement).value)"
        />
        <RuleSchemaEditor
          :schema="mapValueSchema"
          :root-schema="rootSchema"
          :model-value="value"
          :label="`Value for ${key}`"
          :path="`${path}-${key}`"
          :depth="depth + 1"
          @update:model-value="updateMapValue(key, $event)"
        />
        <button type="button" class="quiet-button" @click="removeProperty(key)">
          Remove {{ key }}
        </button>
      </div>
      <button type="button" class="secondary-button" @click="addMapRow">
        Add {{ fieldLabel.toLowerCase() }}
      </button>
    </template>

    <template v-else>
      <label v-if="hasUnionTypeSelector" class="schema-control">
        Value type
        <select
          :value="primitiveType"
          @change="selectUnionType(($event.target as HTMLSelectElement).value)"
        >
          <option v-for="type in unionTypeOptions" :key="type" :value="type">
            {{ type === 'array' ? 'list' : type }}
          </option>
        </select>
      </label>

      <template v-if="primitiveSchema.const !== undefined">
        <p class="fixed-value">{{ primitiveSchema.const }}</p>
      </template>

      <label v-else-if="primitiveType === 'boolean'" class="schema-boolean">
        <input
          type="checkbox"
          :checked="Boolean(modelValue)"
          @change="onBooleanInput"
        />
        {{ fieldLabel }}
      </label>

      <label v-else-if="enumOptions.length" class="schema-control">
        {{ fieldLabel }}
        <select :value="inputValue" @change="onEnumInput">
          <option
            v-for="option in enumOptions"
            :key="String(option)"
            :value="String(option)"
          >
            {{ option }}
          </option>
        </select>
      </label>

      <label v-else class="schema-control">
        {{ fieldLabel }}
        <textarea
          v-if="
            primitiveType === 'string' && (effectiveSchema.maxLength ?? 0) > 160
          "
          :value="inputValue"
          rows="3"
          @input="onPrimitiveInput"
        />
        <input
          v-else
          :value="inputValue"
          :type="primitiveType === 'integer' ? 'number' : 'text'"
          :step="primitiveType === 'integer' ? 1 : undefined"
          :min="effectiveSchema.minimum"
          :max="effectiveSchema.maximum"
          :maxlength="effectiveSchema.maxLength"
          :placeholder="
            effectiveSchema.format === 'date-time'
              ? '2026-01-01T00:00:00Z'
              : undefined
          "
          @input="onPrimitiveInput"
        />
      </label>
      <p v-if="effectiveSchema.description" class="schema-description">
        {{ effectiveSchema.description }}
      </p>
    </template>
  </fieldset>
</template>

<style scoped>
.schema-editor {
  min-width: 0;
  margin: 0;
  padding: 0.9rem;
  border: 1px solid var(--color-border);
  border-radius: 0.65rem;
}
.schema-editor-nested {
  background: var(--color-surface);
}
legend {
  padding: 0 0.3rem;
  font-size: 0.9rem;
  font-weight: 650;
}
.schema-field {
  margin: 0.7rem 0;
}
.schema-enable,
.schema-boolean {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--color-muted);
  font-size: 0.9rem;
}
.schema-control {
  display: grid;
  gap: 0.35rem;
  max-width: 42rem;
  color: var(--color-brand-900);
  font-size: 0.9rem;
  font-weight: 600;
}
input,
select,
textarea {
  width: 100%;
  min-height: 2.65rem;
  padding: 0.55rem 0.65rem;
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
textarea {
  resize: vertical;
}
.schema-array-item,
.schema-map-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: end;
  gap: 0.6rem;
  margin: 0.6rem 0;
}
.schema-map-row {
  grid-template-columns: minmax(8rem, 0.8fr) minmax(12rem, 1.5fr) auto;
}
.schema-map-row > label {
  display: grid;
  gap: 0.3rem;
  color: var(--color-brand-900);
}
.fixed-value {
  margin: 0.3rem 0;
  color: var(--color-muted);
}
.schema-description {
  margin: 0.3rem 0 0;
  color: var(--color-muted);
  font-size: 0.84rem;
  line-height: 1.45;
}
.secondary-button,
.quiet-button {
  min-height: 2.35rem;
  padding: 0.4rem 0.7rem;
  border: 1px solid var(--color-border-strong);
  border-radius: 0.45rem;
  color: var(--color-brand-900);
  background: var(--color-surface);
  font: inherit;
  cursor: pointer;
}
.quiet-button {
  color: var(--color-muted);
  font-size: 0.85rem;
}
.secondary-button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}
@media (max-width: 720px) {
  .schema-map-row {
    grid-template-columns: 1fr;
  }
}
</style>
