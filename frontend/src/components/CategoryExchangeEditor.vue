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
const directionLabel = (direction: string) =>
  ({
    sent: 'Sent',
    received: 'Received',
    both: 'Both',
    entry: 'Entry',
  })[direction] ?? direction
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
function valueTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    text: 'Text',
    integer: 'Integer',
    callsign: 'Callsign',
    serial: 'Serial number',
    enum: 'Enumeration',
    grid: 'Grid locator',
    zone: 'Zone',
  }
  return labels[type] ? labels[type] : type
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
        <strong>{{ $tr('Dimensions') }}</strong>
        {{
          $tr(
            'are separate entry-classification axes, such as operator, power, band, mode, or assistance. Their choices are the values entrants may select, and together they determine the result categories. Stable keys are used in saved rules and data; labels are shown to entrants. Built-in labels follow their presets; custom labels can be changed without changing the stable key. Mark a dimension required only if the sponsor requires an entrant to choose one. “Requires declaration” means the choice needs an entry declaration such as a section or station class. Use mutually exclusive groups only for combinations the sponsor disallows.',
          )
        }}
      </p>
      <article v-for="(row, index) in rows" :key="index" class="controlled-row">
        <label
          >{{ $tr('Dimension key')
          }}<select
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
              {{ $tr(label) }} ({{ key }})
            </option>
            <option value="custom">{{ $tr('Custom dimension…') }}</option>
          </select></label
        >
        <label v-if="!categoryDimensions.some(([key]) => key === row.key)"
          >{{ $tr('Custom stable key')
          }}<input
            :value="String(row.key ?? '')"
            @input="
              update(index, { key: ($event.target as HTMLInputElement).value })
            "
        /></label>
        <label
          >{{ $tr('Dimension label')
          }}<select
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
              {{ $tr(label) }}
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
          {{ $tr('Required for entries') }}</label
        >
        <div class="controlled-choice-list">
          <strong>{{ $tr('Allowed choices') }}</strong>
          <div
            v-for="(choice, choiceIndex) in choices(row)"
            :key="choiceIndex"
            class="controlled-choice"
          >
            <label
              >{{ $tr('Choice key')
              }}<select
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
                  {{ $tr(label) }} ({{ key }})
                </option>
                <option value="custom">
                  {{ $tr('Custom choice…') }}
                </option></select
              ><input
                v-if="
                  !(categoryValues[String(row.key)] ?? []).some(
                    ([key]) => key === choice.key,
                  )
                "
                :aria-label="$tr('Custom stable choice key')"
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
              >{{ $tr('Choice label')
              }}<select
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
                  {{ $tr(label) }}
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
              {{ $tr('Requires declaration') }}</label
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
              {{ $tr('Remove choice') }}
            </button>
          </div>
          <button
            type="button"
            class="secondary-button"
            @click="addChoice(index)"
          >
            {{ $tr('Add choice') }}
          </button>
        </div>
        <button type="button" class="quiet-button" @click="remove(index)">
          {{ $tr('Remove dimension') }}
        </button>
      </article>
      <button type="button" class="secondary-button" @click="add">
        {{ $tr('Add dimension') }}
      </button>
      <label class="mutually-exclusive"
        >{{ $tr('Mutually exclusive dimension groups') }}
        <span class="field-help">
          {{
            $tr(
              'Enter stable dimension keys separated by commas, one incompatible group per line. For example, if you define custom dimensions named',
            )
          }}
          <code>single_band</code> {{ $tr('and') }} <code>all_band</code
          >{{
            $tr(
              ', listing both means an entry cannot configure both dimensions.',
            )
          }} </span
        ><textarea
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
        <strong>{{ $tr('Exchange schema') }}</strong>
        {{
          $tr(
            'describes the fields sent and received for each contact, plus values declared once for the whole entry. It is the canonical vocabulary used by validation and scoring; the format mapping section connects these fields to names in uploaded Cabrillo or ADIF logs. Field keys are stable references used by the system; labels are for display. Select a common field to prefill its key, label, type, and direction, or choose “Custom exchange field” for a contest-specific value. Choose “sent”, “received”, or “both” for contact exchanges, and “entry” for a single entry-level declaration. Mark a field required only if the sponsor requires it. Serial scope controls when a sent sequence number increments; enum values restrict accepted text to the listed choices.',
          )
        }}
      </p>
      <article v-for="(row, index) in rows" :key="index" class="controlled-row">
        <label
          >{{ $tr('Field key')
          }}<select
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
              {{ $tr(label) }} ({{ key }})
            </option>
            <option value="custom">{{ $tr('Custom exchange field…') }}</option>
          </select></label
        >
        <label v-if="!exchangeFields.some(([key]) => key === row.key)"
          >{{ $tr('Custom stable key')
          }}<input
            :value="String(row.key ?? '')"
            @input="
              update(index, { key: ($event.target as HTMLInputElement).value })
            "
        /></label>
        <label
          >{{ $tr('Field label')
          }}<select
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
              {{ $tr(label) }}
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
          >{{ $tr('Value type')
          }}<select
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
              :value="type"
            >
              {{ $tr(valueTypeLabel(type)) }}
            </option>
          </select></label
        >
        <label
          >{{ $tr('Direction')
          }}<select
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
              :value="direction"
            >
              {{ $tr(directionLabel(direction)) }}
            </option>
          </select></label
        >
        <label v-if="row.value_type === 'serial'"
          >{{ $tr('Serial increments per')
          }}<select
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
          >{{ $tr('Allowed enum choices')
          }}<input
            :value="
              Array.isArray(row.choices)
                ? (row.choices as string[]).join(', ')
                : ''
            "
            :placeholder="$tr('Comma-separated allowed values')"
            @change="
              setEnumChoices(index, ($event.target as HTMLInputElement).value)
            "
        /></label>
        <label v-if="row.value_type === 'integer'"
          >{{ $tr('Minimum integer')
          }}<input
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
          >{{ $tr('Maximum integer')
          }}<input
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
          {{ $tr('Required') }}</label
        >
        <button type="button" class="quiet-button" @click="remove(index)">
          {{ $tr('Remove field') }}
        </button>
      </article>
      <button type="button" class="secondary-button" @click="add">
        {{ $tr('Add exchange field') }}
      </button>
    </div>
  </section>
</template>

<style scoped>
.controlled-rule-fields p {
  max-width: 62rem;
  line-height: 1.55;
  color: var(--color-muted);
}
.controlled-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 16rem), 1fr));
  align-items: end;
  min-width: 0;
  gap: 0.65rem;
  padding: 0.8rem;
  margin: 0.7rem 0;
  border: 1px solid var(--color-border);
  border-radius: 0.5rem;
}
.controlled-row > label,
.controlled-choice label {
  display: grid;
  min-width: 0;
  gap: 0.3rem;
}
.controlled-row > label:has(input[type='checkbox']) {
  display: flex;
  align-items: center;
  align-self: center;
  gap: 0.45rem;
}
.controlled-row > .quiet-button {
  grid-column: 1 / -1;
  justify-self: end;
}
.controlled-row input:not([type='checkbox']),
.controlled-row select {
  width: 100%;
  min-width: 0;
  min-height: 2.5rem;
  padding: 0.45rem;
  border: 1px solid var(--color-border-strong);
  border-radius: 0.35rem;
}
.controlled-choice-list {
  grid-column: 1 / -1;
  min-width: 0;
}
.controlled-choice-list > strong {
  display: block;
  margin-bottom: 0.35rem;
}
.mutually-exclusive {
  display: grid;
  gap: 0.3rem;
  margin-top: 0.7rem;
}
.controlled-choice {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  align-items: end;
  gap: 0.5rem;
  margin: 0.5rem 0;
}
.controlled-choice > button {
  justify-self: end;
}
.controlled-choice label:has(input[type='checkbox']) {
  align-self: center;
  display: flex;
  align-items: center;
  gap: 0.45rem;
}
.controlled-choice input[type='checkbox'] {
  width: 1.1rem;
  min-height: 1.1rem;
}
.field-help {
  color: var(--color-muted);
  font-size: 0.85rem;
  font-weight: 400;
  line-height: 1.45;
}
@media (max-width: 560px) {
  .controlled-row,
  .controlled-choice {
    grid-template-columns: minmax(0, 1fr);
  }
  .controlled-choice > button {
    justify-self: start;
  }
}
</style>
