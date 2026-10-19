<script setup lang="ts">
import { computed } from 'vue'
import type { JsonSchema } from '../api/rulesets'
import { translateText } from '../i18n'

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
    categoryDimensions?: Array<{
      key: string
      label: string
      choices: Array<{ key: string; label: string }>
    }>
    categoryHeader?: string
    arraySiblings?: unknown[]
    headerKey?: string
    factOptions?: Array<{ value: string; label: string }>
    variableOptions?: Array<{ value: string; label: string }>
    exchangeFieldOptions?: Array<{ value: string; label: string }>
    entryExchangeFieldOptions?: Array<{ value: string; label: string }>
    duplicateScopeOptions?: Array<{ value: string; label: string }>
  }>(),
  {
    label: '',
    path: '',
    depth: 0,
    hiddenProperties: () => [],
    categoryDimensions: () => [],
    categoryHeader: '',
    arraySiblings: () => [],
    headerKey: '',
    factOptions: () => [],
    variableOptions: () => [],
    exchangeFieldOptions: () => [],
    entryExchangeFieldOptions: () => [],
    duplicateScopeOptions: () => [],
  },
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
function displayLabel(source: string): string {
  const dynamicValueLabel = /^Value for (.+)$/.exec(source)
  return dynamicValueLabel
    ? translateText('Value for {key}', { key: dynamicValueLabel[1] })
    : translateText(source)
}
function enumLabel(value: unknown): string {
  if (props.path.endsWith('-source_fact')) {
    const option = props.factOptions.find((item) => item.value === value)
    return (
      option?.label ??
      `${value} (${translateText('Unavailable in this ruleset')})`
    )
  }
  if (props.path.endsWith('-variable')) {
    const option = props.variableOptions.find((item) => item.value === value)
    return option?.label ?? `${value} (${translateText('Unavailable in this ruleset')})`
  }
  if (/-scope-\d+$/.test(props.path)) {
    const option = props.duplicateScopeOptions.find(
      (item) => item.value === value,
    )
    if (option) return translateText(option.label)
  }
  const words = String(value).replaceAll('_', ' ')
  const title = words.replace(/\b\w/g, (letter) => letter.toUpperCase())
  return translateText(title)
}
const isExchangeFieldKey = computed(
  () =>
    props.path.includes('-adif_exchange_fields-') &&
    props.path.endsWith('-field_key'),
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
const unionTypeLabel = (type: string) =>
  translateText(
    (
      {
        string: 'Text',
        integer: 'Integer',
        number: 'Number',
        boolean: 'Boolean',
        array: 'List',
      } as Record<string, string>
    )[type] ?? type,
  )
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
const categoryHeader = computed(() =>
  typeof objectValue.value.external_field === 'string'
    ? objectValue.value.external_field
    : props.categoryHeader,
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
const enumOptions = computed(() => {
  if (props.path.endsWith('-source_fact')) {
    const values = props.factOptions.map((item) => item.value)
    const currentValue = String(props.modelValue ?? '')
    if (currentValue && !values.includes(currentValue))
      values.unshift(currentValue)
    return values
  }
  if (props.path.endsWith('-variable')) {
    const values = props.variableOptions.map((item) => item.value)
    const currentValue = String(props.modelValue ?? '')
    if (currentValue && !values.includes(currentValue)) values.unshift(currentValue)
    return values
  }
  if (/-scope-\d+$/.test(props.path) && props.duplicateScopeOptions.length) {
    const values = props.duplicateScopeOptions.map((item) => item.value)
    const currentValue = String(props.modelValue ?? '')
    if (currentValue && !values.includes(currentValue)) values.unshift(currentValue)
    return values
  }
  const values = primitiveSchema.value.enum ?? []
  if (props.path.includes('-header_fields-') && props.headerKey) {
    const expected =
      props.headerKey === 'callsign'
        ? 'CALLSIGN'
        : props.headerKey === 'contest'
          ? 'CONTEST'
          : 'LOCATION'
    return values.filter((value) => value === expected)
  }
  if (!props.path.endsWith('-external_value') || !props.categoryHeader)
    return values
  const allowed: Record<string, string[]> = {
    'CATEGORY-ASSISTED': ['ASSISTED', 'NON-ASSISTED'],
    'CATEGORY-BAND': [
      'ALL',
      '160M',
      '80M',
      '40M',
      '20M',
      '15M',
      '10M',
      '6M',
      '4M',
      '2M',
      '222',
      '432',
      '902',
      '1.2G',
      '2.3G',
      '3.4G',
      '5.7G',
      '10G',
      '24G',
      '47G',
      '75G',
      '122G',
      '134G',
      '241G',
      'Light',
      'VHF-3-BAND',
      'VHF-FM-ONLY',
    ],
    'CATEGORY-MODE': ['CW', 'DIGI', 'FM', 'RTTY', 'SSB', 'MIXED'],
    'CATEGORY-OPERATOR': ['SINGLE-OP', 'MULTI-OP', 'CHECKLOG'],
    'CATEGORY-POWER': ['HIGH', 'LOW', 'QRP'],
    'CATEGORY-STATION': [
      'DISTRIBUTED',
      'FIXED',
      'MOBILE',
      'PORTABLE',
      'ROVER',
      'ROVER-LIMITED',
      'ROVER-UNLIMITED',
      'EXPEDITION',
      'HQ',
      'SCHOOL',
      'EXPLORER',
    ],
    'CATEGORY-TIME': ['6-HOURS', '8-HOURS', '12-HOURS', '24-HOURS'],
    'CATEGORY-TRANSMITTER': ['ONE', 'TWO', 'LIMITED', 'UNLIMITED', 'SWL'],
    'CATEGORY-OVERLAY': [
      'CLASSIC',
      'ROOKIE',
      'TB-WIRES',
      'YOUTH',
      'NOVICE-TECH',
      'YL',
    ],
  }
  return values.filter((value) =>
    allowed[props.categoryHeader]?.includes(String(value)),
  )
})
const inputValue = computed(() =>
  props.modelValue == null ? '' : String(props.modelValue),
)
const showsLegend = computed(
  () =>
    props.depth === 0 ||
    isObject.value ||
    isArray.value ||
    isMap.value ||
    primitiveSchema.value.const !== undefined,
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
  if (props.path.endsWith('-qso_columns')) {
    const fields = [
      'frequency',
      'mode',
      'date',
      'time',
      'callsign_sent',
      'rst_sent',
      'exchange_sent',
      'callsign_received',
      'rst_received',
      'exchange_received',
      'transmitter',
    ]
    const next = fields.find((field) => !arrayValue.value.includes(field))
    if (!next) return
    setValue([...arrayValue.value, next])
    return
  }
  setValue([
    ...arrayValue.value,
    initialValue(effectiveSchema.value.items ?? {}),
  ])
}

function isQsoColumnList() {
  return props.path.endsWith('-qso_columns')
}

function qsoColumnSelectedElsewhere(index: number, value: unknown) {
  return (
    props.path.includes('-qso_columns-') &&
    props.arraySiblings.some(
      (item, itemIndex) => itemIndex !== index && item === value,
    )
  )
}

function currentQsoColumnIndex() {
  const match = /-qso_columns-(\d+)$/.exec(props.path)
  return match ? Number(match[1]) : -1
}

function currentScopeIndex() {
  const match = /-scope-(\d+)$/.exec(props.path)
  return match ? Number(match[1]) : -1
}

function duplicateScopeSelectedElsewhere(value: unknown) {
  const currentIndex = currentScopeIndex()
  return (
    currentIndex >= 0 &&
    props.arraySiblings.some(
      (item, itemIndex) => itemIndex !== currentIndex && item === value,
    )
  )
}

function moveArrayItem(index: number, offset: number) {
  const target = index + offset
  if (!isQsoColumnList() || target < 0 || target >= arrayValue.value.length)
    return
  if (
    (arrayValue.value[index] === 'transmitter' && offset < 0) ||
    (arrayValue.value[target] === 'transmitter' && offset > 0)
  )
    return
  const next = [...arrayValue.value]
  ;[next[index], next[target]] = [next[target], next[index]]
  setValue(next)
}

function removeArrayItem(index: number) {
  setValue(arrayValue.value.filter((_, itemIndex) => itemIndex !== index))
}

function mapRows() {
  return Object.entries(objectValue.value)
}

function addMapRow() {
  const values = objectValue.value
  if (props.path.endsWith('-category_values')) {
    const dimension = props.categoryDimensions.find(
      (item) => !Object.hasOwn(values, item.key),
    )
    if (!dimension) return
    setValue({ ...values, [dimension.key]: dimension.choices[0]?.key ?? '' })
    return
  }
  if (props.path.endsWith('-header_fields')) {
    const header = [
      'callsign',
      'contest',
      ...props.entryExchangeFieldOptions.map((item) => item.value),
    ].find(
      (item) => !Object.hasOwn(values, item),
    )
    if (!header) return
    setValue({
      ...values,
      [header]:
        header === 'callsign'
          ? 'CALLSIGN'
          : header === 'contest'
            ? 'CONTEST'
            : 'LOCATION',
    })
    return
  }
  let key = 'value'
  let suffix = 2
  while (Object.hasOwn(values, key)) {
    key = `value-${suffix}`
    suffix += 1
  }
  setValue({ ...values, [key]: initialValue(mapValueSchema.value) })
}

function categoryForDimension(key: string) {
  return props.categoryDimensions.find((item) => item.key === key)
}

function isCategoryValuesMap() {
  return props.path.endsWith('-category_values')
}

function isHeaderFieldsMap() {
  return props.path.endsWith('-header_fields')
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
    <legend v-if="showsLegend && (label || effectiveSchema.title)">
      {{ displayLabel(fieldLabel) }}
    </legend>

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
              {{ displayLabel(childSchema.title || key.replaceAll('_', ' ')) }}
            </label>
            <p v-if="childSchema.description" class="schema-description">
              {{ displayLabel(childSchema.description) }}
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
              {{ $tr('Configure') }}
              {{ displayLabel(childSchema.title || key.replaceAll('_', ' ')) }}
            </label>
            <RuleSchemaEditor
              v-if="isRequired(key) || Object.hasOwn(objectValue, key)"
              :schema="childSchema"
              :root-schema="rootSchema"
              :model-value="objectValue[key] ?? initialValue(childSchema)"
              :label="
                key === 'kind'
                  ? ''
                  : displayLabel(childSchema.title || key.replaceAll('_', ' '))
              "
              :path="`${path}-${key}`"
              :depth="depth + 1"
              :hidden-properties="hiddenProperties"
              :category-dimensions="categoryDimensions"
              :category-header="categoryHeader"
              :fact-options="factOptions"
              :variable-options="variableOptions"
              :exchange-field-options="exchangeFieldOptions"
              :entry-exchange-field-options="entryExchangeFieldOptions"
              :duplicate-scope-options="duplicateScopeOptions"
              @update:model-value="updateProperty(key, $event)"
            />
          </template>
        </div>
      </template>
    </template>

    <template v-else-if="isArray">
      <p v-if="effectiveSchema.description" class="schema-description">
        {{ displayLabel(effectiveSchema.description) }}
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
          :array-siblings="arrayValue"
          :category-dimensions="categoryDimensions"
          :category-header="categoryHeader"
          :fact-options="factOptions"
          :variable-options="variableOptions"
          :exchange-field-options="exchangeFieldOptions"
          :entry-exchange-field-options="entryExchangeFieldOptions"
          :duplicate-scope-options="duplicateScopeOptions"
          @update:model-value="updateArrayItem(index, $event)"
        />
        <div v-if="isQsoColumnList()" class="schema-array-order">
          <button
            type="button"
            class="quiet-button"
            :disabled="index === 0"
            @click="moveArrayItem(index, -1)"
          >
            {{ $tr('Move up') }}
          </button>
          <button
            type="button"
            class="quiet-button"
            :disabled="index === arrayValue.length - 1"
            @click="moveArrayItem(index, 1)"
          >
            {{ $tr('Move down') }}
          </button>
        </div>
        <button
          v-if="!isQsoColumnList() || item === 'transmitter'"
          type="button"
          class="quiet-button"
          @click="removeArrayItem(index)"
        >
          {{ $tr('Remove') }}
        </button>
      </div>
      <button
        type="button"
        class="secondary-button"
        :disabled="arrayValue.length >= (effectiveSchema.maxItems ?? 500)"
        @click="addArrayItem"
      >
        {{ $tr('Add') }} {{ fieldLabel.toLowerCase() }}
      </button>
    </template>

    <template v-else-if="isMap">
      <p v-if="effectiveSchema.description" class="schema-description">
        {{ displayLabel(effectiveSchema.description) }}
      </p>
      <div
        v-for="([key, value], index) in mapRows()"
        :key="key"
        class="schema-map-row"
      >
        <div class="schema-map-key">
          <label :for="`${path}-${index}-key`">{{ $tr('Key') }}</label>
          <select
            v-if="isCategoryValuesMap()"
            :id="`${path}-${index}-key`"
            :value="key"
            @change="
              renameMapKey(key, ($event.target as HTMLSelectElement).value)
            "
          >
            <option
              v-for="dimension in categoryDimensions"
              :key="dimension.key"
              :value="dimension.key"
              :disabled="
                dimension.key !== key &&
                Object.hasOwn(objectValue, dimension.key)
              "
            >
              {{ dimension.label }} ({{ dimension.key }})
            </option>
          </select>
          <select
            v-else-if="isHeaderFieldsMap()"
            :id="`${path}-${index}-key`"
            :value="key"
            @change="
              renameMapKey(key, ($event.target as HTMLSelectElement).value)
            "
          >
            <option
              value="callsign"
              :disabled="key !== 'callsign' && Object.hasOwn(objectValue, 'callsign')"
            >
              CALLSIGN
            </option>
            <option
              value="contest"
              :disabled="key !== 'contest' && Object.hasOwn(objectValue, 'contest')"
            >
              CONTEST
            </option>
            <option
              v-for="field in entryExchangeFieldOptions"
              :key="field.value"
              :value="field.value"
              :disabled="key !== field.value && Object.hasOwn(objectValue, field.value)"
            >
              {{ $tr(field.label) }} ({{ field.value }})
            </option>
          </select>
          <input
            v-else
            :id="`${path}-${index}-key`"
            :value="key"
            autocomplete="off"
            @change="
              renameMapKey(key, ($event.target as HTMLInputElement).value)
            "
          />
        </div>
        <div class="schema-map-value">
          <label v-if="isCategoryValuesMap()" class="schema-control">
            {{ displayLabel(`Value for ${key}`) }}
            <select
              :value="String(value)"
              @change="
                updateMapValue(key, ($event.target as HTMLSelectElement).value)
              "
            >
              <option
                v-for="choice in categoryForDimension(key)?.choices ?? []"
                :key="choice.key"
                :value="choice.key"
              >
                {{ choice.label }} ({{ choice.key }})
              </option>
            </select>
          </label>
          <RuleSchemaEditor
            v-else
            :schema="mapValueSchema"
            :root-schema="rootSchema"
            :model-value="value"
            :label="`Value for ${key}`"
            :path="`${path}-${key}`"
            :depth="depth + 1"
            :category-dimensions="categoryDimensions"
            :header-key="isHeaderFieldsMap() ? key : ''"
            :fact-options="factOptions"
            :variable-options="variableOptions"
            :exchange-field-options="exchangeFieldOptions"
            :entry-exchange-field-options="entryExchangeFieldOptions"
            :duplicate-scope-options="duplicateScopeOptions"
            @update:model-value="updateMapValue(key, $event)"
          />
        </div>
        <button type="button" class="quiet-button" @click="removeProperty(key)">
          {{ $tr('Remove') }} {{ key }}
        </button>
      </div>
      <button type="button" class="secondary-button" @click="addMapRow">
        {{ $tr('Add') }} {{ fieldLabel.toLowerCase() }}
      </button>
    </template>

    <template v-else>
      <label v-if="hasUnionTypeSelector" class="schema-control">
        {{ $tr('Value type') }}
        <select
          :value="primitiveType"
          @change="selectUnionType(($event.target as HTMLSelectElement).value)"
        >
          <option v-for="type in unionTypeOptions" :key="type" :value="type">
            {{ unionTypeLabel(type) }}
          </option>
        </select>
      </label>

      <template v-if="primitiveSchema.const !== undefined">
        <p class="fixed-value">{{ primitiveSchema.const }}</p>
      </template>

      <label v-else-if="isExchangeFieldKey" class="schema-control">
        {{ displayLabel(fieldLabel) }}
        <select
          :value="inputValue"
          @change="setValue(($event.target as HTMLSelectElement).value)"
        >
          <option v-if="!inputValue" value="" disabled>
            {{ $tr('Choose an exchange field') }}
          </option>
          <option
            v-for="option in exchangeFieldOptions"
            :key="option.value"
            :value="option.value"
          >
            {{ $tr(option.label) }}
          </option>
        </select>
      </label>

      <label v-else-if="primitiveType === 'boolean'" class="schema-boolean">
        <input
          type="checkbox"
          :checked="Boolean(modelValue)"
          @change="onBooleanInput"
        />
        {{ displayLabel(fieldLabel) }}
      </label>

      <label v-else-if="enumOptions.length" class="schema-control">
        {{ displayLabel(fieldLabel) }}
        <select :value="inputValue" @change="onEnumInput">
          <option
            v-if="path.endsWith('-source_fact') && !inputValue"
            value=""
            disabled
          >
            {{ $tr('Choose a fact') }}
          </option>
          <option
            v-for="option in enumOptions"
            :key="String(option)"
            :value="String(option)"
            :disabled="
              qsoColumnSelectedElsewhere(currentQsoColumnIndex(), option) ||
              (/-scope-\d+$/.test(path) &&
                duplicateScopeSelectedElsewhere(option))
            "
          >
            {{ enumLabel(option) }}
          </option>
        </select>
      </label>

      <label v-else class="schema-control">
        {{ displayLabel(fieldLabel) }}
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
        {{ displayLabel(effectiveSchema.description) }}
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
  background: var(--color-surface-muted);
}
.schema-editor-nested {
  min-width: 0;
  padding: 0.35rem 0 0;
  border: 0;
  border-radius: 0;
  background: transparent;
}
legend {
  padding: 0 0.3rem;
  font-size: 0.9rem;
  font-weight: 650;
}
.schema-editor-nested > legend {
  padding: 0;
  color: var(--color-brand-900);
}
.schema-field {
  min-width: 0;
  margin: 0.65rem 0;
  padding: 0 0 0.65rem;
  border-bottom: 1px solid var(--color-border);
}
.schema-field:last-child {
  padding-bottom: 0;
  border-bottom: 0;
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
  width: 100%;
  max-width: 52rem;
  min-width: 0;
  color: var(--color-brand-900);
  font-size: 0.9rem;
  font-weight: 600;
  line-height: 1.35;
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
  grid-template-columns: minmax(0, 1fr) max-content;
  align-items: end;
  gap: 0.6rem;
  margin: 0.6rem 0;
}
.schema-map-row {
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.5fr) max-content;
  align-items: start;
}
.schema-map-key {
  display: grid;
  min-width: 0;
  gap: 0.35rem;
}
.schema-map-key label {
  display: grid;
  gap: 0.35rem;
  color: var(--color-brand-900);
  font-size: 0.9rem;
  font-weight: 600;
  line-height: 1.35;
}
.schema-map-value {
  min-width: 0;
}
.schema-map-value > .schema-editor-nested {
  padding-top: 0;
}
.schema-map-row > .quiet-button {
  align-self: end;
  justify-self: start;
}
.fixed-value {
  margin: 0.3rem 0;
  color: var(--color-muted);
}
.schema-description {
  max-width: 70rem;
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
  .schema-array-item {
    grid-template-columns: minmax(0, 1fr);
  }
  .schema-map-row {
    grid-template-columns: minmax(0, 1fr);
  }
  .schema-map-row > .quiet-button {
    justify-self: start;
  }
}
</style>
