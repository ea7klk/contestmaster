<script setup lang="ts">
import { computed } from 'vue'

type Row = Record<string, unknown>
const props = defineProps<{
  kind: 'categories' | 'exchange'
  modelValue: Row
}>()
const emit = defineEmits<{ 'update:modelValue': [value: Row] }>()

const categoryDimensions = [
  ['operator', 'Operator'],
  ['power', 'Power'],
  ['band', 'Band'],
  ['mode', 'Mode'],
  ['assisted', 'Assistance'],
  ['transmitter', 'Transmitters'],
  ['overlay', 'Overlay'],
  ['station_class', 'Station class'],
  ['region', 'Region'],
  ['category', 'Contest category'],
]
const categoryValues: Record<string, Array<[string, string]>> = {
  operator: [
    ['single', 'Single operator'],
    ['multi', 'Multi operator'],
    ['multi_single', 'Multi operator, single transmitter'],
  ],
  power: [
    ['qrp', 'QRP'],
    ['low', 'Low power'],
    ['high', 'High power'],
  ],
  band: [
    ['all', 'All band'],
    ['single', 'Single band'],
  ],
  mode: [
    ['mixed', 'Mixed mode'],
    ['cw', 'CW'],
    ['phone', 'Phone'],
    ['digital', 'Digital'],
  ],
  assisted: [
    ['assisted', 'Assisted'],
    ['unassisted', 'Unassisted'],
  ],
  transmitter: [
    ['one', 'One transmitter'],
    ['two', 'Two transmitters'],
    ['unlimited', 'Unlimited'],
  ],
}
const exchangeFields = [
  ['rst', 'Signal report', 'text', 'both'],
  ['serial', 'Serial number', 'serial', 'both'],
  ['cq_zone', 'CQ Zone', 'zone', 'received'],
  ['itu_zone', 'ITU Zone', 'zone', 'received'],
  ['section', 'Section', 'text', 'received'],
  ['grid', 'Grid locator', 'grid', 'received'],
  ['state', 'State', 'text', 'received'],
  ['province', 'Province', 'text', 'received'],
  ['check', 'Check', 'integer', 'received'],
  ['precedence', 'Precedence', 'enum', 'received'],
  ['call_area', 'Call area', 'text', 'received'],
  ['power', 'Power', 'enum', 'received'],
]
const fieldsName = computed(() =>
  props.kind === 'categories' ? 'dimensions' : 'fields',
)
const rows = computed<Row[]>(() =>
  Array.isArray(props.modelValue[fieldsName.value])
    ? (props.modelValue[fieldsName.value] as Row[])
    : [],
)
function updateRows(next: Row[]) {
  emit('update:modelValue', { ...props.modelValue, [fieldsName.value]: next })
}
function add() {
  updateRows([
    ...rows.value,
    props.kind === 'categories'
      ? {
          key: 'operator',
          label: 'Operator',
          required: true,
          choices: [
            {
              key: 'single',
              label: 'Single operator',
              requires_declaration: false,
            },
          ],
        }
      : {
          key: 'serial',
          label: 'Serial number',
          value_type: 'serial',
          direction: 'both',
          required: true,
          choices: [],
          max_length: 256,
          serial_scope: 'entry',
        },
  ])
}
function remove(index: number) {
  updateRows(rows.value.filter((_row, i) => i !== index))
}
function update(index: number, values: Row) {
  updateRows(
    rows.value.map((row, i) => (i === index ? { ...row, ...values } : row)),
  )
}
function choices(row: Row) {
  return Array.isArray(row.choices) ? (row.choices as Row[]) : []
}
function updateChoices(rowIndex: number, next: Row[]) {
  update(rowIndex, { choices: next })
}
function setEnumChoices(rowIndex: number, raw: string) {
  update(rowIndex, {
    choices: raw
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean),
  })
}
function setInteger(
  rowIndex: number,
  key: 'min_integer' | 'max_integer',
  raw: string,
) {
  update(rowIndex, { [key]: raw ? Number(raw) : null })
}
function integerField(value: unknown): number | undefined {
  return typeof value === 'number' ? value : undefined
}
function addChoice(rowIndex: number) {
  const choicesForRow = choices(rows.value[rowIndex] ?? {})
  updateChoices(rowIndex, [
    ...choicesForRow,
    { key: 'custom', label: 'Custom value', requires_declaration: false },
  ])
}
function setPreset(index: number, key: string) {
  if (key === 'custom') return update(index, { key: '', label: '' })
  if (props.kind === 'categories')
    update(index, {
      key,
      label: categoryDimensions.find(([value]) => value === key)?.[1] ?? key,
      choices: (categoryValues[key] ?? []).map(([choiceKey, label]) => ({
        key: choiceKey,
        label,
        requires_declaration: false,
      })),
    })
  else {
    const preset = exchangeFields.find(([value]) => value === key)
    if (preset)
      update(index, {
        key: preset[0],
        label: preset[1],
        value_type: preset[2],
        direction: preset[3],
        ...(preset[2] === 'serial' ? { serial_scope: 'entry' } : {}),
      })
  }
}
function setChoice(index: number, choiceIndex: number, key: string) {
  const row = rows.value[index] ?? {}
  const dimensionKey = String(row.key ?? '')
  const options = categoryValues[dimensionKey] ?? []
  const old = choices(row)[choiceIndex] ?? {}
  const preset = options.find(([value]) => value === key)
  const next = choices(row).map((item, i) =>
    i === choiceIndex
      ? preset
        ? { ...item, key: preset[0], label: preset[1] }
        : { ...item, key: '', label: '' }
      : item,
  )
  updateChoices(index, next)
  void old
}
</script>

<template>
  <section class="controlled-rule-fields">
    <div v-if="kind === 'categories'">
      <p>
        <strong>Dimensions</strong> are separate entry-classification axes, such
        as operator, power, or band. Their choices are the values entrants may
        select. Keys stay stable when a display label changes. Choose “Custom
        dimension” to define a contest-specific axis.
      </p>
      <article v-for="(row, index) in rows" :key="index" class="controlled-row">
        <label
          >Dimension key<select
            :value="
              categoryDimensions.some(([key]) => key === row.key)
                ? row.key
                : 'custom'
            "
            @change="
              setPreset(index, ($event.target as HTMLSelectElement).value)
            "
          >
            <option
              v-for="[key, label] in categoryDimensions"
              :key="key"
              :value="key"
            >
              {{ label }} ({{ key }})
            </option>
            <option value="custom">Custom dimension…</option>
          </select></label
        >
        <label v-if="!categoryDimensions.some(([key]) => key === row.key)"
          >Custom stable key<input
            :value="String(row.key ?? '')"
            @input="
              update(index, { key: ($event.target as HTMLInputElement).value })
            "
        /></label>
        <label
          >Dimension label<select
            v-if="categoryDimensions.some(([key]) => key === row.key)"
            :value="String(row.label ?? '')"
            @change="
              update(index, {
                label: ($event.target as HTMLSelectElement).value,
              })
            "
          >
            <option
              v-for="[key, label] in categoryDimensions"
              v-show="key === row.key"
              :key="key"
              :value="label"
            >
              {{ label }}
            </option></select
          ><input
            v-else
            :value="String(row.label ?? '')"
            @input="
              update(index, {
                label: ($event.target as HTMLInputElement).value,
              })
            "
        /></label>
        <label
          ><input
            type="checkbox"
            :checked="row.required !== false"
            @change="
              update(index, {
                required: ($event.target as HTMLInputElement).checked,
              })
            "
          />
          Required for entries</label
        >
        <div class="controlled-choice-list">
          <strong>Allowed choices</strong>
          <div
            v-for="(choice, choiceIndex) in choices(row)"
            :key="choiceIndex"
            class="controlled-choice"
          >
            <label
              >Choice key<select
                :value="
                  (categoryValues[String(row.key)] ?? []).some(
                    ([key]) => key === choice.key,
                  )
                    ? choice.key
                    : 'custom'
                "
                @change="
                  setChoice(
                    index,
                    choiceIndex,
                    ($event.target as HTMLSelectElement).value,
                  )
                "
              >
                <option
                  v-for="[key, label] in categoryValues[String(row.key)] ?? []"
                  :key="key"
                  :value="key"
                >
                  {{ label }} ({{ key }})
                </option>
                <option value="custom">Custom choice…</option></select
              ><input
                v-if="
                  !(categoryValues[String(row.key)] ?? []).some(
                    ([key]) => key === choice.key,
                  )
                "
                aria-label="Custom stable choice key"
                :value="String(choice.key ?? '')"
                @input="
                  updateChoices(
                    index,
                    choices(row).map((item, i) =>
                      i === choiceIndex
                        ? {
                            ...item,
                            key: ($event.target as HTMLInputElement).value,
                          }
                        : item,
                    ),
                  )
                "
            /></label>
            <label
              >Choice label<select
                v-if="
                  (categoryValues[String(row.key)] ?? []).some(
                    ([key]) => key === choice.key,
                  )
                "
                :value="String(choice.label ?? '')"
                @change="
                  updateChoices(
                    index,
                    choices(row).map((item, i) =>
                      i === choiceIndex
                        ? {
                            ...item,
                            label: ($event.target as HTMLSelectElement).value,
                          }
                        : item,
                    ),
                  )
                "
              >
                <option
                  v-for="[key, label] in categoryValues[String(row.key)] ?? []"
                  v-show="key === choice.key"
                  :key="key"
                  :value="label"
                >
                  {{ label }}
                </option></select
              ><input
                v-else
                :value="String(choice.label ?? '')"
                @input="
                  updateChoices(
                    index,
                    choices(row).map((item, i) =>
                      i === choiceIndex
                        ? {
                            ...item,
                            label: ($event.target as HTMLInputElement).value,
                          }
                        : item,
                    ),
                  )
                "
            /></label>
            <label
              ><input
                type="checkbox"
                :checked="choice.requires_declaration === true"
                @change="
                  updateChoices(
                    index,
                    choices(row).map((item, i) =>
                      i === choiceIndex
                        ? {
                            ...item,
                            requires_declaration: (
                              $event.target as HTMLInputElement
                            ).checked,
                          }
                        : item,
                    ),
                  )
                "
              />
              Requires declaration</label
            >
            <button
              type="button"
              class="quiet-button"
              @click="
                updateChoices(
                  index,
                  choices(row).filter((_item, i) => i !== choiceIndex),
                )
              "
            >
              Remove choice
            </button>
          </div>
          <button
            type="button"
            class="secondary-button"
            @click="addChoice(index)"
          >
            Add choice
          </button>
        </div>
        <button type="button" class="quiet-button" @click="remove(index)">
          Remove dimension
        </button>
      </article>
      <button type="button" class="secondary-button" @click="add">
        Add dimension
      </button>
      <label class="mutually-exclusive"
        >Mutually exclusive dimension groups (one comma-separated key group per
        line)<textarea
          :value="
            Array.isArray(modelValue.mutually_exclusive)
              ? (modelValue.mutually_exclusive as string[][])
                  .map((group) => group.join(', '))
                  .join('\n')
              : ''
          "
          rows="2"
          @change="
            emit('update:modelValue', {
              ...modelValue,
              mutually_exclusive: ($event.target as HTMLTextAreaElement).value
                .split('\n')
                .map((line) =>
                  line
                    .split(',')
                    .map((key) => key.trim())
                    .filter(Boolean),
                )
                .filter((group) => group.length > 1),
            })
          "
        />
      </label>
    </div>
    <div v-else>
      <p>
        <strong>Exchange schema</strong> describes the fields sent and received
        for each contact, plus entry-level declarations. Field keys are stable
        references; labels are for display. Select a common field to prefill its
        key, label, type, and direction, or choose “Custom exchange field” for a
        contest-specific value.
      </p>
      <article v-for="(row, index) in rows" :key="index" class="controlled-row">
        <label
          >Field key<select
            :value="
              exchangeFields.some(([key]) => key === row.key)
                ? row.key
                : 'custom'
            "
            @change="
              setPreset(index, ($event.target as HTMLSelectElement).value)
            "
          >
            <option
              v-for="[key, label] in exchangeFields"
              :key="key"
              :value="key"
            >
              {{ label }} ({{ key }})
            </option>
            <option value="custom">Custom exchange field…</option>
          </select></label
        >
        <label v-if="!exchangeFields.some(([key]) => key === row.key)"
          >Custom stable key<input
            :value="String(row.key ?? '')"
            @input="
              update(index, { key: ($event.target as HTMLInputElement).value })
            "
        /></label>
        <label
          >Field label<select
            v-if="exchangeFields.some(([key]) => key === row.key)"
            :value="String(row.label ?? '')"
            @change="
              update(index, {
                label: ($event.target as HTMLSelectElement).value,
              })
            "
          >
            <option
              v-for="[key, label] in exchangeFields"
              v-show="key === row.key"
              :key="key"
              :value="label"
            >
              {{ label }}
            </option></select
          ><input
            v-else
            :value="String(row.label ?? '')"
            @input="
              update(index, {
                label: ($event.target as HTMLInputElement).value,
              })
            "
        /></label>
        <label
          >Value type<select
            :value="String(row.value_type ?? 'text')"
            @change="
              update(index, {
                value_type: ($event.target as HTMLSelectElement).value,
              })
            "
          >
            <option
              v-for="type in [
                'text',
                'integer',
                'callsign',
                'serial',
                'enum',
                'grid',
                'zone',
              ]"
              :key="type"
            >
              {{ type }}
            </option>
          </select></label
        >
        <label
          >Direction<select
            :value="String(row.direction ?? 'both')"
            @change="
              update(index, {
                direction: ($event.target as HTMLSelectElement).value,
              })
            "
          >
            <option
              v-for="direction in ['sent', 'received', 'both', 'entry']"
              :key="direction"
            >
              {{ direction }}
            </option>
          </select></label
        >
        <label v-if="row.value_type === 'serial'"
          >Serial increments per<select
            :value="String(row.serial_scope ?? 'entry')"
            @change="
              update(index, {
                serial_scope: ($event.target as HTMLSelectElement).value,
              })
            "
          >
            <option
              v-for="scope in ['entry', 'band', 'mode', 'transmitter']"
              :key="scope"
            >
              {{ scope }}
            </option>
          </select></label
        >
        <label v-if="row.value_type === 'enum'"
          >Allowed enum choices<input
            :value="
              Array.isArray(row.choices)
                ? (row.choices as string[]).join(', ')
                : ''
            "
            placeholder="Comma-separated allowed values"
            @change="
              setEnumChoices(index, ($event.target as HTMLInputElement).value)
            "
        /></label>
        <label v-if="row.value_type === 'integer'"
          >Minimum integer<input
            type="number"
            :value="integerField(row.min_integer)"
            @input="
              setInteger(
                index,
                'min_integer',
                ($event.target as HTMLInputElement).value,
              )
            "
        /></label>
        <label v-if="row.value_type === 'integer'"
          >Maximum integer<input
            type="number"
            :value="integerField(row.max_integer)"
            @input="
              setInteger(
                index,
                'max_integer',
                ($event.target as HTMLInputElement).value,
              )
            "
        /></label>
        <label
          ><input
            type="checkbox"
            :checked="row.required !== false"
            @change="
              update(index, {
                required: ($event.target as HTMLInputElement).checked,
              })
            "
          />
          Required</label
        >
        <button type="button" class="quiet-button" @click="remove(index)">
          Remove field
        </button>
      </article>
      <button type="button" class="secondary-button" @click="add">
        Add exchange field
      </button>
    </div>
  </section>
</template>

<style scoped>
.controlled-rule-fields p {
  max-width: 62rem;
  line-height: 1.55;
  color: #425965;
}
.controlled-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
  gap: 0.65rem;
  padding: 0.8rem;
  margin: 0.7rem 0;
  border: 1px solid #d4dfe4;
  border-radius: 0.5rem;
}
.controlled-row > label,
.controlled-choice label {
  display: grid;
  gap: 0.3rem;
}
.controlled-row input:not([type='checkbox']),
.controlled-row select {
  min-height: 2.5rem;
  padding: 0.45rem;
  border: 1px solid #aebfc8;
  border-radius: 0.35rem;
}
.controlled-choice-list {
  grid-column: 1 / -1;
}
.mutually-exclusive {
  display: grid;
  gap: 0.3rem;
  margin-top: 0.7rem;
}
.controlled-choice {
  display: grid;
  grid-template-columns: 1fr 1fr auto;
  align-items: end;
  gap: 0.5rem;
  margin: 0.5rem 0;
}
</style>
