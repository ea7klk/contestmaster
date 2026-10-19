<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import ConditionEditor from '../components/ConditionEditor.vue'
import RuleSchemaEditor from '../components/RuleSchemaEditor.vue'
import CategoryExchangeEditor from '../components/CategoryExchangeEditor.vue'
import EligibilityCatalogEditor from '../components/EligibilityCatalogEditor.vue'
import ResourceAdministrators from '../components/ResourceAdministrators.vue'
import { translateText } from '../i18n'
import { availableMultiplierSourceFacts } from './multiplierSourceFacts'
import {
  getBands,
  getModes,
  type OperatingCatalogItem,
} from '../api/operatingCatalog'
import {
  getRuleCatalog,
  getSavedRulesetVersion,
  RulesetApiError,
  saveRulesetVersion,
  validateRuleset,
  type JsonSchema,
  type RulesetDraft,
  type RuleTypeDescriptor,
  type RulesetIssue,
  type RulesetValidationResponse,
} from '../api/rulesets'

interface ConfiguredRuleDraft {
  id: string
  rule: Record<string, unknown>
  when?: Record<string, unknown>
}

const catalog = ref<RuleTypeDescriptor[]>([])
const operatingCatalog = ref<OperatingCatalogItem[]>([])
const rules = ref<ConfiguredRuleDraft[]>([])
const rulesetKey = ref('my-contest')
const version = ref('1')
const sourceUrl = ref('')
const sourceEdition = ref('')
const selectedType = ref('')
const catalogLoading = ref(true)
const validating = ref(false)
const savingVersion = ref(false)
const savedMessage = ref('')
const validation = ref<RulesetValidationResponse | null>(null)
const issues = ref<RulesetIssue[]>([])
const generalError = ref('')
const fileInput = ref<HTMLInputElement | null>(null)
const editingSource = ref('')
const activeRulesetId = ref<number | null>(null)
const props = defineProps<{ editVersionId?: string }>()

const currentStep = ref(1)
const stepAnnouncement = ref('')
const STEPS = [
  {
    number: 1,
    title: 'Ruleset identity',
    description: 'Identify the official rules and version.',
  },
  {
    number: 2,
    title: 'Categories and exchange',
    description: 'Define entrant classes and contact exchanges.',
  },
  {
    number: 3,
    title: 'Logs and contacts',
    description: 'Choose log formats and decide which contacts count.',
  },
  {
    number: 4,
    title: 'Scoring',
    description:
      'Set integer points, multipliers, bonuses, penalties, and formula.',
  },
  {
    number: 5,
    title: 'Limits and review',
    description:
      'Configure optional limits, review, and validate the complete draft.',
  },
] as const
const RULE_STEP: Record<string, number> = {
  categories: 2,
  exchange: 2,
  submission: 3,
  format_mapping: 3,
  eligibility: 3,
  duplicates: 3,
  points: 4,
  distance_points: 4,
  multiplier: 4,
  bonus: 4,
  penalty: 4,
  score_formula: 4,
  operating_constraints: 5,
  workflow_hook: 5,
}
const activeStep = computed(
  () => STEPS.find((step) => step.number === currentStep.value) ?? STEPS[0],
)
const stepOptionalTypes = computed(() =>
  optionalTypes.value.filter(
    (type) => RULE_STEP[type.key] === currentStep.value,
  ),
)

const optionalTypes = computed(() =>
  catalog.value.filter((type) => !type.required),
)
const usedSingletonKinds = computed(
  () => new Set(rules.value.map((item) => String(item.rule.kind))),
)
const categoryDimensions = computed(() => {
  const categoryRule = rules.value.find(
    (item) => item.rule.kind === 'categories',
  )
  const dimensions = categoryRule?.rule.dimensions
  if (!Array.isArray(dimensions)) return []
  return dimensions.flatMap((dimension) => {
    if (!dimension || typeof dimension !== 'object') return []
    const record = dimension as Record<string, unknown>
    if (typeof record.key !== 'string' || !Array.isArray(record.choices))
      return []
    return [
      {
        key: record.key,
        label: typeof record.label === 'string' ? record.label : record.key,
        choices: record.choices.flatMap((choice) => {
          if (!choice || typeof choice !== 'object') return []
          const item = choice as Record<string, unknown>
          return typeof item.key === 'string'
            ? [
                {
                  key: item.key,
                  label: typeof item.label === 'string' ? item.label : item.key,
                },
              ]
            : []
        }),
      },
    ]
  })
})
const multiplierSourceFacts = computed(() =>
  availableMultiplierSourceFacts(rules.value),
)
const cabrilloExchangeMapPreview = computed(() => {
  const exchangeRule = rules.value.find(
    (item) => item.rule.kind === 'exchange',
  )?.rule
  const fields = Array.isArray(exchangeRule?.fields)
    ? (exchangeRule.fields as Array<Record<string, unknown>>)
    : []
  return [
    { column: 'rst_sent', direction: 'sent', fieldKey: 'rst' },
    { column: 'exchange_sent', direction: 'sent', fieldKey: null },
    { column: 'rst_received', direction: 'received', fieldKey: 'rst' },
    { column: 'exchange_received', direction: 'received', fieldKey: null },
  ].flatMap((mapping) => {
    const mapped = fields
      .filter((field) => {
        if (field.direction !== mapping.direction && field.direction !== 'both')
          return false
        return mapping.fieldKey === 'rst'
          ? field.key === 'rst'
          : field.key !== 'rst' && field.direction !== 'entry'
      })
      .map((field) => String(field.label ?? field.key ?? ''))
      .filter(Boolean)
    return mapped.length ? [{ column: mapping.column, fields: mapped }] : []
  })
})
const adifExchangeFieldPreview = computed(() => {
  const exchangeRule = rules.value.find(
    (item) => item.rule.kind === 'exchange',
  )?.rule
  const fields = Array.isArray(exchangeRule?.fields)
    ? (exchangeRule.fields as Array<Record<string, unknown>>)
    : []
  const adifFields: Record<string, string[]> = {
    serial: ['STX', 'SRX'],
    report: ['RST_SENT', 'RST_RCVD'],
    grid: ['MY_GRIDSQUARE', 'GRIDSQUARE'],
    state: ['MY_STATE', 'STATE'],
    cq_zone: ['MY_CQ_ZONE', 'CQZ'],
    itu_zone: ['MY_ITU_ZONE', 'ITUZ'],
  }
  return fields.map((field) => ({
    label: typeof field.label === 'string' ? field.label : String(field.key),
    key: String(field.key ?? ''),
    tags: adifFields[String(field.key)] ?? ['STX_STRING', 'SRX_STRING'],
  }))
})
function resolveSchema(schema: JsonSchema, rootSchema = schema): JsonSchema {
  if (schema.$ref) {
    const name = schema.$ref.split('/').at(-1) ?? ''
    return rootSchema.$defs?.[name] ?? schema
  }
  if (schema.anyOf)
    return schema.anyOf.find((option) => option.type !== 'null') ?? schema
  return schema
}

function initialValue(input: JsonSchema, rootSchema: JsonSchema): unknown {
  if (input.default !== undefined) return input.default
  const schema = resolveSchema(input, rootSchema)
  if (schema.const !== undefined) return schema.const
  if (schema.default !== undefined) return schema.default
  if (schema.enum?.length) return schema.enum[0]
  if (schema.type === 'object') {
    const result: Record<string, unknown> = {}
    for (const [key, child] of Object.entries(schema.properties ?? {})) {
      if (
        schema.required?.includes(key) ||
        child.default !== undefined ||
        child.const !== undefined
      ) {
        result[key] = initialValue(child, rootSchema)
      }
    }
    return result
  }
  if (schema.type === 'array') {
    const itemSchema = schema.items ?? {}
    return Array.from({ length: Math.min(schema.minItems ?? 0, 5) }, () =>
      initialValue(itemSchema, rootSchema),
    )
  }
  if (schema.type === 'boolean') return false
  if (schema.type === 'integer' || schema.type === 'number')
    return schema.minimum ?? 0
  return ''
}

function descriptorFor(kind: string) {
  return catalog.value.find((item) => item.key === kind)
}

function newRule(kind: string, idNumber: number): ConfiguredRuleDraft | null {
  const descriptor = descriptorFor(kind)
  if (!descriptor) return null
  const rule = initialValue(descriptor.schema, descriptor.schema) as Record<
    string,
    unknown
  >
  if (kind === 'exchange') {
    rule.fields = [
      {
        key: 'rst',
        label: 'Signal report',
        value_type: 'text',
        direction: 'both',
        required: true,
        max_length: 256,
      },
      {
        key: 'exchange',
        label: 'Contest exchange',
        value_type: 'text',
        direction: 'both',
        required: true,
        max_length: 256,
      },
    ]
  }
  if (kind === 'format_mapping' && rule.format === 'cabrillo') {
    rule.qso_columns = [...CABRILLO_REQUIRED_COLUMNS]
  }
  return {
    id: `${kind.replaceAll('_', '-')}-${idNumber}`,
    rule,
  }
}

const CABRILLO_REQUIRED_COLUMNS = [
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
]
const CABRILLO_CATEGORY_HEADERS: Record<string, string[]> = {
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
    'LIGHT',
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

function normalizeCabrilloColumns(items: ConfiguredRuleDraft[]) {
  return items.map((item) => {
    const rule = { ...item.rule }
    if (rule.kind === 'format_mapping' && rule.format === 'cabrillo') {
      const columns = Array.isArray(rule.qso_columns)
        ? rule.qso_columns.filter(
            (column): column is string => typeof column === 'string',
          )
        : []
      const uniqueColumns = [...new Set(columns)]
      const complete = CABRILLO_REQUIRED_COLUMNS.every((column) =>
        uniqueColumns.includes(column),
      )
      const unique = columns.length === uniqueColumns.length
      rule.qso_columns =
        complete && unique
          ? columns
          : [
              ...CABRILLO_REQUIRED_COLUMNS,
              ...(uniqueColumns.includes('transmitter') ? ['transmitter'] : []),
            ]
      if (Array.isArray(rule.category_mappings)) {
        rule.category_mappings = rule.category_mappings.map((rawMapping) => {
          if (!rawMapping || typeof rawMapping !== 'object') return rawMapping
          const mapping = rawMapping as Record<string, unknown>
          if (typeof mapping.external_field === 'string') return mapping
          const externalValue = String(
            mapping.external_value ?? '',
          ).toUpperCase()
          const externalField = Object.entries(CABRILLO_CATEGORY_HEADERS).find(
            ([, values]) => values.includes(externalValue),
          )?.[0]
          return externalField
            ? { ...mapping, external_field: externalField }
            : mapping
        })
      }
    }
    return { ...item, rule }
  })
}

function seedRequiredRules() {
  rules.value = catalog.value
    .filter((descriptor) => descriptor.required)
    .map((descriptor, index) => newRule(descriptor.key, index + 1))
    .filter((rule): rule is ConfiguredRuleDraft => rule !== null)
}

function addSelectedRule() {
  if (!selectedType.value) return
  if (
    ['submission', 'categories', 'format_mapping', 'score_formula'].includes(
      selectedType.value,
    ) &&
    usedSingletonKinds.value.has(selectedType.value)
  ) {
    return
  }
  const rule = newRule(selectedType.value, rules.value.length + 1)
  if (rule) rules.value.push(rule)
  selectedType.value = ''
  clearValidation()
}

function removeRule(index: number) {
  if (
    catalog.value.find((type) => type.key === rules.value[index]?.rule.kind)
      ?.required
  )
    return
  rules.value.splice(index, 1)
  clearValidation()
}

function supportsConditions(rule: ConfiguredRuleDraft) {
  return ![
    'submission',
    'categories',
    'format_mapping',
    'score_formula',
  ].includes(String(rule.rule.kind))
}

function ruleStep(kind: unknown): number {
  return RULE_STEP[String(kind)] ?? 3
}

function rulesOnStep(stepNumber: number): ConfiguredRuleDraft[] {
  return rules.value.filter((item) => ruleStep(item.rule.kind) === stepNumber)
}

function stepSummary(stepNumber: number): string {
  if (stepNumber === 1) {
    const provenance = [sourceUrl.value, sourceEdition.value].filter(
      Boolean,
    ).length
    return translateText('{key} · version {version} · {count} source details', {
      key: rulesetKey.value || translateText('Ruleset'),
      version: version.value || translateText('No version'),
      count: provenance,
    })
  }
  if (stepNumber === 2) {
    const categoryRule = rulesOnStep(2).find(
      (item) => item.rule.kind === 'categories',
    )
    const exchangeRule = rulesOnStep(2).find(
      (item) => item.rule.kind === 'exchange',
    )
    const dimensionCount = Array.isArray(categoryRule?.rule.dimensions)
      ? categoryRule.rule.dimensions.length
      : 0
    const fieldCount = Array.isArray(exchangeRule?.rule.fields)
      ? exchangeRule.rule.fields.length
      : 0
    return translateText('{dimensions} dimensions · {fields} exchange fields', {
      dimensions: dimensionCount,
      fields: fieldCount,
    })
  }
  if (stepNumber === 3) {
    const formats = rulesOnStep(3)
      .filter((item) => item.rule.kind === 'format_mapping')
      .map((item) => String(item.rule.format ?? '').toUpperCase())
      .filter(Boolean)
    const latePolicy = rulesOnStep(3).find(
      (item) => item.rule.kind === 'submission',
    )?.rule.late_policy
    return translateText('{formats} · late policy: {policy}', {
      formats: formats.length
        ? formats.join(', ')
        : translateText('No format selected'),
      policy: String(latePolicy ?? translateText('Not set')),
    })
  }
  if (stepNumber === 4) {
    const scoringRules = rulesOnStep(4)
    const multiplierCount = scoringRules.filter(
      (item) => item.rule.kind === 'multiplier',
    ).length
    return translateText('{rules} scoring rules · {multipliers} multipliers', {
      rules: scoringRules.length,
      multipliers: multiplierCount,
    })
  }
  const operationalRules = rulesOnStep(5)
  return translateText('{count} optional limits or review workflows', {
    count: operationalRules.length,
  })
}

function goToStep(stepNumber: number) {
  currentStep.value = Math.min(STEPS.length, Math.max(1, stepNumber))
  stepAnnouncement.value = translateText('Step {step} of 5: {title}', {
    step: currentStep.value,
    title: translateText(activeStep.value.title),
  })
  void nextTick(() => {
    document.getElementById('active-step-title')?.focus()
  })
}

async function openValidationIssue(issue: RulesetIssue) {
  const match = issue.location.join('.').match(/rules\[(\d+)\]/)
  const index = match ? Number(match[1]) : -1
  const stepNumber = index >= 0 ? ruleStep(rules.value[index]?.rule.kind) : 1
  currentStep.value = stepNumber
  stepAnnouncement.value = translateText('Step {step} of 5: {title}', {
    step: stepNumber,
    title: translateText(activeStep.value.title),
  })
  await nextTick()
  if (index >= 0) {
    const card = document.getElementById(`rule-card-${index}`)
    if (card?.tagName === 'DETAILS') {
      card.setAttribute('open', '')
      card.querySelector('summary')?.focus()
    }
  } else {
    document.getElementById('active-step-title')?.focus()
  }
}

function setCondition(
  rule: ConfiguredRuleDraft,
  condition: Record<string, unknown> | undefined,
) {
  if (condition) rule.when = condition
  else delete rule.when
  clearValidation()
}

function setEligibilityCondition(
  rule: ConfiguredRuleDraft,
  condition: Record<string, unknown> | undefined,
) {
  const next = { ...rule.rule }
  if (condition) next.eligible_if = condition
  else delete next.eligible_if
  rule.rule = next
  clearValidation()
}

function updateRule(rule: ConfiguredRuleDraft, value: unknown) {
  const updated = value as Record<string, unknown>
  rule.rule =
    updated.kind === 'format_mapping' && updated.format === 'cabrillo'
      ? (normalizeCabrilloColumns([{ ...rule, rule: updated }])[0]?.rule ??
        updated)
      : updated
  clearValidation()
}

function selectedValues(
  rule: ConfiguredRuleDraft,
  key: 'allowed_bands' | 'allowed_modes',
) {
  return Array.isArray(rule.rule[key]) ? (rule.rule[key] as string[]) : []
}

function setSelectedValues(
  rule: ConfiguredRuleDraft,
  key: 'allowed_bands' | 'allowed_modes',
  values: string[] | undefined,
) {
  const next = { ...rule.rule }
  if (values) next[key] = values
  else delete next[key]
  rule.rule = next
  clearValidation()
}

const helpText: Record<string, string> = {
  submission:
    'The contest editor owns the event start, event end, recurrence, and UTC log-submission cutoff. This reusable rule only describes what the system does with a log received after that contest cutoff: reject it, accept and mark it late, or accept it for checklog review. Enable a manager extension only when the sponsor permits an explicit extension; it does not change the original cutoff automatically.',
  categories:
    'Use these dimensions and choices to define the entrant classes shown in results. The controls below explain stable keys, required choices, declarations, and incompatible combinations.',
  exchange:
    'Define the canonical values used to validate contacts and entrant declarations. The controls below explain field keys, labels, directions, value types, and serial settings; format mappings connect these values to uploaded log fields.',
  eligibility:
    'This rule determines which submitted contacts may count before points and multipliers are applied. Use band and mode selections when the sponsor restricts operating segments; leave those lists unrestricted when any catalog value is allowed. Add a condition for geography or other supported contact facts only when the written rules define that limit. The built-in checks can reject self-contacts, out-of-period contacts, and missing required exchange data. Select whether a failed check is uncredited or held for review.',
  duplicates:
    'Choose the values that make two contacts count as the same contact. Worked callsign is always part of the identity; adding band, mode, grid, or transmitter makes otherwise repeated contacts distinct when that value changes. For example, callsign plus band permits one contact per station on each band. Then choose the sponsor’s consequence for another contact in the same scope: ignore it, leave it uncredited, apply an integer penalty, or send it for review. Duplicate contacts never earn QSO points. Enable “Count for multipliers” only when the sponsor allows a duplicate to supply a new multiplier; the duplicate must still pass the other eligibility checks. This option defaults off.',
  points:
    'This rule assigns the base integer points for each eligible contact, before multiplier and bonus rules. Fixed points give every eligible contact the same value. A lookup assigns a value by one supported fact, such as band, mode, entity, zone, or an exchange field. Add a default only if the sponsor defines what to do when the fact has no matching lookup entry. Every value must be an integer at least zero; do not convert fractional point rules into decimals.',
  distance_points:
    'Use this when the sponsor awards points from the distance between station locations. The entrant locator comes from each ADIF QSO MY_GRIDSQUARE value when present, otherwise the station locator; Cabrillo uses the GRID-LOCATOR header. The worked station locator is a received grid exchange. Contestmaster calculates great-circle distance between locator cell centers using the selected 4, 6, or 8 character precision, then awards integer points per commenced kilometer. Same-cell contacts use the configured same-grid points. Choose review or not credited when either locator is missing or invalid.',
  multiplier:
    'A multiplier is a distinct value that increases the score according to the contest formula. Choose the submitted or resolved fact that supplies the value, then choose where uniqueness resets: once for the whole contest, per band, per mode, per band and mode, per grid, or per transmitter. Multiple contacts can earn points while the same multiplier value is counted only once within its configured scope. Use the scope stated in the sponsor rules.',
  bonus:
    'Use a bonus for additional integer points awarded per eligible contact or once per entry. Set a cap when the sponsor limits the total, and set a minimum eligible-contact count when a threshold applies. If proof or a declaration is required, choose its stable evidence key; the bonus is awarded only when that declaration is present. Keep ordinary per-contact points in QSO Points instead.',
  penalty:
    'Add one penalty rule for each distinct violation and consequence described by the sponsor. Give the reason a stable code so score explanations can identify it. Choose whether the violation removes a contact, deducts integer points, reclassifies the entry, disqualifies it, or sends it for review. Point deductions require a positive integer; set the maximum number of times this penalty can apply to one entry.',
  score_formula:
    'This is the final arithmetic applied after contacts, multipliers, bonuses, and penalties have been determined. Select the starting score and add operations in the same order as the published formula. Each step consumes the prior integer result and another supported integer variable or constant. Division must specify its integer rounding rule. Review the worked example after validation; it demonstrates the formula with sample values and is not a prediction of an entrant’s score. Example: 120 points × 8 multipliers + 10 bonus − 5 penalty = 965.',
  operating_constraints:
    'Use this rule for entry-level or operating limits the engine can check, such as required off-time periods, a maximum number of transmitters, or a permitted band/mode combination. Add only constraints supported by the shown fields and the official rules. Choose whether a violation is uncredited or requires human review when the result is ambiguous.',
  format_mapping:
    'This rule describes how an uploaded log format maps to the canonical station, contact, and exchange fields configured above. Add one mapping for every file format the contest accepts; do not add a format just because it appears in the menu unless the application supports its importer. Cabrillo and ADI/ADIF upload parsing are implemented; CSV and native JSON are descriptive options only. Map sponsor-specific exchange names to stable field keys. Unrecognized source fields can be preserved for later review.',
  workflow_hook:
    'Workflow hooks describe cross-log comparisons, review, publication, or award behavior that affects more than one contact. Enable a hook only when the sponsor’s rules require that workflow and its configured settings express the rule. Hooks do not execute arbitrary code; unsupported or ambiguous cases must be reviewed rather than guessed.',
}

const scoringExamples: Record<string, string> = {
  distance_points:
    'Example: with 6-character grid centers, a 4.2 km contact is 5 commenced kilometers and earns 5 points at 1 point per kilometer. Two contacts in the same 6-character cell use the configured same-grid score instead.',
  score_formula:
    'Example: 120 QSO points × 8 multiplier credits + 10 bonus points − 5 penalty points = 965 final points. Operations run from top to bottom, and each result is an integer.',
  multiplier:
    'Example: when entity multipliers reset per band, working entity EA on 20 m five times counts once; working EA again on 40 m counts a second time. The contest earns 2 multiplier credits.',
  bonus:
    'Example: a 2-point bonus per eligible QSO, capped at 20 points, gives 14 points for 7 qualifying contacts and no more than 20 for 10 or more. A per-entry bonus is awarded once after its configured minimum-contact threshold.',
  penalty:
    'Example: a 5-point deduction with a maximum of 2 occurrences deducts at most 10 points, even if the entry has more violations. Non-point actions such as reclassification or disqualification do not change the points total directly.',
}

function buildDraft(): RulesetDraft {
  const draft: RulesetDraft = {
    schema_version: 2,
    ruleset_key: rulesetKey.value.trim(),
    version: version.value.trim(),
    rules: rules.value.map((item) => ({
      id: item.id.trim(),
      rule: item.rule,
      ...(item.when ? { when: item.when } : {}),
    })),
  }
  if (sourceUrl.value.trim()) draft.source_url = sourceUrl.value.trim()
  if (sourceEdition.value.trim())
    draft.source_edition = sourceEdition.value.trim()
  return draft
}

async function validateDraft() {
  if (!version.value.trim()) {
    generalError.value =
      'Enter a new version identifier before validating this ruleset.'
    return
  }
  validating.value = true
  generalError.value = ''
  issues.value = []
  validation.value = null
  savedMessage.value = ''
  try {
    validation.value = await validateRuleset(buildDraft())
  } catch (error) {
    if (error instanceof RulesetApiError) {
      generalError.value = error.message
      issues.value = error.issues
    } else {
      generalError.value = 'The draft could not be validated.'
    }
  } finally {
    validating.value = false
  }
}

async function persistDraft() {
  if (savingVersion.value) return
  if (!version.value.trim()) {
    generalError.value =
      'Enter a new version identifier before saving this ruleset.'
    return
  }
  savingVersion.value = true
  generalError.value = ''
  savedMessage.value = ''
  try {
    const persisted = await saveRulesetVersion(buildDraft())
    activeRulesetId.value = persisted.ruleset_id ?? null
    savedMessage.value = persisted.created
      ? editingSource.value
        ? `Saved ${persisted.ruleset_key} version ${persisted.version}. ${editingSource.value} remains unchanged; select the new version from the contest manager when ready.`
        : `Saved ${persisted.ruleset_key} version ${persisted.version}. Assign it from the contest manager.`
      : `This exact ${persisted.ruleset_key} version ${persisted.version} is already saved.`
  } catch (error) {
    if (error instanceof RulesetApiError) {
      generalError.value = error.message
      issues.value = error.issues
    } else {
      generalError.value = 'The ruleset version could not be saved.'
    }
  } finally {
    savingVersion.value = false
  }
}

function clearValidation() {
  validation.value = null
  issues.value = []
  generalError.value = ''
  savedMessage.value = ''
}

async function loadSavedVersion(
  versionId: number,
  signal?: Parameters<typeof getSavedRulesetVersion>[1],
) {
  const saved = await getSavedRulesetVersion(versionId, signal)
  activeRulesetId.value = saved.ruleset_id ?? null
  const definition = saved.configuration
  if (
    !Array.isArray(definition.rules) ||
    typeof definition.ruleset_key !== 'string' ||
    typeof definition.version !== 'string'
  ) {
    throw new Error('The saved ruleset has an invalid configuration.')
  }
  rulesetKey.value = definition.ruleset_key
  version.value = definition.version
  sourceUrl.value = definition.source_url ?? ''
  sourceEdition.value = definition.source_edition ?? ''
  rules.value = normalizeCabrilloColumns(
    definition.rules.map((item) => ({ ...item })),
  )
  editingSource.value = `${definition.ruleset_key} version ${definition.version}`
  clearValidation()
  savedMessage.value = `Loaded ${editingSource.value}. Enter a new version identifier to save your changes.`
}

function exportDraft() {
  const blob = new Blob([`${JSON.stringify(buildDraft(), null, 2)}\n`], {
    type: 'application/json',
  })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `${rulesetKey.value || 'ruleset'}-${version.value || 'draft'}.json`
  link.click()
  URL.revokeObjectURL(link.href)
}

function normalizeImportedRule(item: RulesetDraft['rules'][number]) {
  const rule = { ...item.rule }
  if (rule.kind === 'bonus' && Object.hasOwn(rule, 'evidence_required')) {
    const legacyRequired = rule.evidence_required
    const hasEvidenceKey =
      rule.evidence_key !== undefined && rule.evidence_key !== null
    if (
      typeof legacyRequired !== 'boolean' ||
      legacyRequired !== hasEvidenceKey
    ) {
      throw new Error(
        'Legacy bonus evidence_required must agree with whether evidence_key is set.',
      )
    }
    delete rule.evidence_required
  }
  return { ...item, rule }
}

async function importDraft(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  clearValidation()
  generalError.value = ''
  try {
    const parsed = JSON.parse(await file.text()) as {
      schema_version: number
      ruleset_key: string
      version: string
      source_url?: string
      source_edition?: string
      rules: RulesetDraft['rules']
    }
    if (
      !Array.isArray(parsed.rules) ||
      typeof parsed.ruleset_key !== 'string' ||
      ![1, 2].includes(parsed.schema_version)
    ) {
      throw new Error('This file does not look like a ruleset draft.')
    }
    rulesetKey.value = parsed.ruleset_key
    version.value = parsed.version
    sourceUrl.value = parsed.source_url ?? ''
    sourceEdition.value = parsed.source_edition ?? ''
    const removedSchedule = parsed.rules.some(
      (item) => item.rule.kind === 'schedule',
    )
    const normalizedRules = parsed.rules
      .filter((item) => item.rule.kind !== 'schedule')
      .map((item) => {
        if (item.rule.kind !== 'submission') return item
        const rule = { ...item.rule }
        delete rule.cutoff_mode
        delete rule.cutoff_utc
        delete rule.minutes_after_contest
        return { ...item, rule }
      })
      .map(normalizeImportedRule)
    rules.value = normalizeCabrilloColumns(
      normalizedRules.map((item) => ({ ...item })),
    )
    if (parsed.schema_version === 1 || removedSchedule) {
      savedMessage.value =
        'Imported a legacy draft. Configure contest dates, periodicity, and submission cutoff in contest configuration.'
    }
  } catch (error) {
    generalError.value =
      error instanceof Error
        ? error.message
        : 'The selected file is not valid JSON.'
  } finally {
    if (fileInput.value) fileInput.value.value = ''
  }
}

function displayIssue(issue: RulesetIssue) {
  const path = issue.location.length ? `${issue.location.join(' › ')}: ` : ''
  return `${path}${issue.message}`
}

onMounted(async () => {
  const controller = new AbortController()
  try {
    const [ruleCatalogResult, bandsResult, modesResult] =
      await Promise.allSettled([
        getRuleCatalog(controller.signal),
        getBands(controller.signal),
        getModes(controller.signal),
      ])
    if (ruleCatalogResult.status === 'rejected') {
      throw new Error(
        `The built-in rule catalog could not be loaded: ${catalogErrorMessage(ruleCatalogResult.reason)}`,
      )
    }
    if (bandsResult.status === 'rejected') {
      throw new Error(
        `The band catalog could not be loaded: ${catalogErrorMessage(bandsResult.reason)}`,
      )
    }
    if (modesResult.status === 'rejected') {
      throw new Error(
        `The mode catalog could not be loaded: ${catalogErrorMessage(modesResult.reason)}`,
      )
    }
    catalog.value = ruleCatalogResult.value.rule_types
    operatingCatalog.value = [
      ...bandsResult.value.items,
      ...modesResult.value.items,
    ]
    if (props.editVersionId !== undefined) {
      const versionId = Number(props.editVersionId)
      if (!Number.isSafeInteger(versionId) || versionId < 1) {
        throw new Error('The requested saved ruleset version is invalid.')
      }
      await loadSavedVersion(versionId, controller.signal)
    } else {
      seedRequiredRules()
    }
  } catch (error) {
    generalError.value =
      error instanceof Error
        ? error.message
        : 'The rule catalog could not be loaded.'
  } finally {
    catalogLoading.value = false
  }
})

watch(
  () => props.editVersionId,
  async (versionId) => {
    if (catalogLoading.value) return
    generalError.value = ''
    savedMessage.value = ''
    editingSource.value = ''
    if (versionId === undefined) {
      seedRequiredRules()
      return
    }
    const parsedId = Number(versionId)
    if (!Number.isSafeInteger(parsedId) || parsedId < 1) {
      generalError.value = 'The requested saved ruleset version is invalid.'
      return
    }
    try {
      await loadSavedVersion(parsedId)
    } catch (error) {
      generalError.value =
        error instanceof Error
          ? error.message
          : 'The saved ruleset could not be loaded.'
    }
  },
)

function catalogErrorMessage(reason: unknown) {
  return reason instanceof Error
    ? reason.message
    : 'The API returned an unknown error.'
}
</script>

<template>
  <section class="composer-page" aria-labelledby="composer-title">
    <p class="eyebrow">{{ $tr('Contest manager tools') }}</p>
    <h1 id="composer-title">{{ $tr('Ruleset composer') }}</h1>
    <p class="intro">
      {{
        $tr(
          'Turn the sponsor’s published rules into a reusable, versioned set of configuration. The API validates the settings and explains the scoring behavior; it remains authoritative when the contest is run.',
        )
      }}
    </p>
    <a class="secondary-button back-link" href="/manage/rulesets">{{
      $tr('← Back to rulesets')
    }}</a>

    <p v-if="generalError" role="alert" class="error-panel">
      {{ $tr(generalError) }}
    </p>
    <p v-if="savedMessage" role="status" class="notice">
      {{ $tr(savedMessage) }}
    </p>
    <p v-if="catalogLoading" role="status" class="notice">
      {{ $tr('Loading the built-in rule catalog…') }}
    </p>
    <template v-else-if="catalog.length">
      <nav class="step-navigation" :aria-label="$tr('Ruleset creation steps')">
        <ol>
          <li v-for="step in STEPS" :key="step.number">
            <button
              type="button"
              :class="{ 'is-current': currentStep === step.number }"
              :aria-current="currentStep === step.number ? 'step' : undefined"
              @click="goToStep(step.number)"
            >
              <span class="step-number">{{ step.number }}</span>
              <span>{{ $tr(step.title) }}</span>
            </button>
          </li>
        </ol>
      </nav>
      <p class="step-status" role="status" aria-live="polite">
        {{
          stepAnnouncement ||
          $tr('Step {step} of 5: {title}', {
            step: currentStep,
            title: $tr(activeStep.title),
          })
        }}
      </p>

      <div class="builder-layout">
        <div class="builder-main">
          <header class="step-content">
            <h2 id="active-step-title" tabindex="-1">
              {{
                $tr(
                  currentStep === 5 ? 'Review your ruleset' : activeStep.title,
                )
              }}
            </h2>
            <p class="step-description">{{ $tr(activeStep.description) }}</p>
            <p v-if="currentStep === 1" class="review-reminder">
              {{
                $tr(
                  'Check every prefilled setting against the sponsor’s official rules. Defaults are starting values, not confirmation of a contest requirement.',
                )
              }}
            </p>
          </header>
          <fieldset v-show="currentStep === 1" class="panel metadata-panel">
            <legend>{{ $tr('Ruleset identity') }}</legend>
            <p class="section-help">
              {{
                $tr(
                  'These values identify the reusable configuration and its source. A saved version is immutable; changing its settings requires a new version identifier.',
                )
              }}
            </p>
            <div class="metadata-grid">
              <label>
                <span class="metadata-field-label">{{
                  $tr('Ruleset key')
                }}</span>
                <input
                  v-model="rulesetKey"
                  maxlength="120"
                  autocomplete="off"
                  @input="clearValidation"
                />
                <span class="field-help">
                  {{
                    $tr(
                      'Stable, lowercase identifier for this family of rules, such as',
                    )
                  }}
                  <code>spring-sprint</code
                  >{{
                    $tr(
                      '. Keep it the same when saving a later version of the same contest rules.',
                    )
                  }}
                </span>
              </label>
              <label>
                <span class="metadata-field-label">{{ $tr('Version') }}</span>
                <input
                  v-model="version"
                  maxlength="80"
                  autocomplete="off"
                  required
                  @input="clearValidation"
                />
                <span v-if="editingSource" class="field-help">
                  {{ $tr('Editing') }} {{ editingSource
                  }}{{
                    $tr(
                      '. Enter a new version identifier; saved versions cannot be changed.',
                    )
                  }}
                </span>
                <span v-else class="field-help">
                  {{
                    $tr(
                      'Use a year, edition, or other unique label. Validation requires a version, and each saved version is a permanent snapshot.',
                    )
                  }}
                </span>
              </label>
              <label>
                <span class="metadata-field-label">
                  {{ $tr('Published rules URL') }}
                  <span class="optional-label">{{ $tr('Optional') }}</span>
                </span>
                <input
                  v-model="sourceUrl"
                  type="url"
                  maxlength="2048"
                  autocomplete="url"
                  @input="clearValidation"
                />
                <span class="field-help">
                  {{
                    $tr(
                      'Link the official rules page or document used to configure this version. The contest sponsor’s rules remain authoritative.',
                    )
                  }}
                </span>
              </label>
              <label>
                <span class="metadata-field-label">
                  {{ $tr('Source edition or year') }}
                  <span class="optional-label">{{ $tr('Optional') }}</span>
                </span>
                <input
                  v-model="sourceEdition"
                  maxlength="120"
                  @input="clearValidation"
                />
                <span class="field-help">
                  {{
                    $tr(
                      'Record the published year or edition so managers can tell which revision of the sponsor’s rules this version follows.',
                    )
                  }}
                </span>
              </label>
            </div>
          </fieldset>

          <section
            v-if="currentStep === 5"
            class="review-groups"
            aria-labelledby="review-groups-title"
          >
            <p id="review-groups-title" class="step-description">
              {{
                $tr(
                  'Check the summary against the sponsor rules. Use Edit to revisit any section; no setting is omitted from the saved draft.',
                )
              }}
            </p>
            <article
              v-for="step in STEPS.slice(0, 4)"
              :key="step.number"
              class="review-group"
            >
              <div>
                <h3>{{ $tr(step.title) }}</h3>
                <p>{{ stepSummary(step.number) }}</p>
              </div>
              <button
                type="button"
                class="secondary-button"
                @click="goToStep(step.number)"
              >
                {{ $tr('Edit section') }}
              </button>
            </article>
            <p class="review-reminder">
              {{
                $tr(
                  'The sponsor’s published rules remain authoritative. If a requirement cannot be expressed by these settings, record the gap rather than approximating it.',
                )
              }}
            </p>
          </section>

          <section
            v-show="currentStep >= 2"
            aria-labelledby="configured-rules-title"
            class="rules-section"
          >
            <div class="section-heading">
              <div>
                <h2 id="configured-rules-title" tabindex="-1">
                  {{ $tr(activeStep.title) }}
                </h2>
                <p>{{ $tr(activeStep.description) }}</p>
              </div>
              <div v-if="stepOptionalTypes.length" class="add-rule-control">
                <label for="add-rule-type">
                  {{
                    $tr(
                      currentStep === 4
                        ? 'Add a scoring rule'
                        : 'Add a limit or review rule',
                    )
                  }}
                  <select id="add-rule-type" v-model="selectedType">
                    <option value="">{{ $tr('Choose a rule type') }}</option>
                    <option
                      v-for="type in stepOptionalTypes"
                      :key="type.key"
                      :value="type.key"
                    >
                      {{ $tr(type.label) }}
                    </option>
                  </select>
                </label>
                <button
                  type="button"
                  class="secondary-button"
                  :disabled="!selectedType"
                  @click="addSelectedRule"
                >
                  {{ $tr('Add rule') }}
                </button>
              </div>
            </div>

            <p v-if="currentStep === 2" class="step-hint">
              {{
                $tr(
                  'Required: define categories and the exchange. Custom dimensions and exchange fields remain available when the sponsor uses non-standard terms.',
                )
              }}
            </p>
            <p v-else-if="currentStep === 3" class="step-hint">
              {{
                $tr(
                  'Choose only formats supported by this application and specified by the sponsor. Contest dates and the submission cutoff are configured on the contest, not here. New Cabrillo mappings include the required WWROF QSO columns. The generic sent and received exchange columns carry the ordered fields from the exchange schema; they are not one column per exchange field.',
                )
              }}
            </p>
            <p v-else-if="currentStep === 4" class="step-hint">
              {{
                $tr(
                  'Every score value stays an integer. Add optional scoring rules only when the published rules require them.',
                )
              }}
            </p>
            <p v-else-if="currentStep === 5" class="step-hint">
              {{
                $tr(
                  'Operating limits and cross-log or review workflows are optional. Add only behavior required by the official rules.',
                )
              }}
            </p>

            <details
              v-for="(configured, index) in rules"
              v-show="ruleStep(configured.rule.kind) === currentStep"
              :id="`rule-card-${index}`"
              :key="configured.id"
              class="rule-card"
            >
              <summary class="rule-card-heading">
                <span class="rule-card-title">
                  <strong>{{
                    $tr(
                      String(
                        descriptorFor(String(configured.rule.kind))?.label ??
                          configured.rule.kind,
                      ),
                    )
                  }}</strong>
                  <small>{{
                    $tr(
                      String(
                        descriptorFor(String(configured.rule.kind))
                          ?.description ?? '',
                      ),
                    )
                  }}</small>
                </span>
                <span
                  v-if="descriptorFor(String(configured.rule.kind))?.required"
                  class="required-badge"
                  >{{ $tr('Required') }}</span
                >
                <span v-else class="optional-badge">{{ $tr('Optional') }}</span>
              </summary>
              <div class="rule-card-body">
                <p
                  v-if="helpText[String(configured.rule.kind)]"
                  class="rule-explanation"
                >
                  {{ $tr(helpText[String(configured.rule.kind)] ?? '') }}
                </p>
                <div
                  v-if="
                    configured.rule.kind === 'format_mapping' &&
                    configured.rule.format === 'cabrillo'
                  "
                  class="exchange-map-preview"
                >
                  <strong>{{
                    $tr('Exchange fields mapped automatically')
                  }}</strong>
                  <ul>
                    <li
                      v-for="mapping in cabrilloExchangeMapPreview"
                      :key="mapping.column"
                    >
                      <code>{{ mapping.column }}</code>
                      ←
                      {{ mapping.fields.map((label) => $tr(label)).join(', ') }}
                    </li>
                  </ul>
                  <p>
                    {{
                      $tr(
                        'This preview follows the exchange schema. Exchange fields are read in their configured order from the generic Cabrillo exchange column; no new JSON mapping fields are added.',
                      )
                    }}
                  </p>
                </div>
                <section
                  v-if="
                    configured.rule.kind === 'format_mapping' &&
                    configured.rule.format === 'adif'
                  "
                  class="exchange-map-preview adif-field-preview"
                  aria-label="ADIF field mapping preview"
                  data-testid="adif-field-preview"
                >
                  <strong>{{ $tr('ADIF fields used by the importer') }}</strong>
                  <p>
                    {{
                      $tr(
                        'Every QSO needs CALL, QSO_DATE, TIME_ON, and MODE (or SUBMODE), plus BAND or FREQ. These are importer requirements; the ADIF standard itself does not mandate a universal QSO field set.',
                      )
                    }}
                  </p>
                  <ul>
                    <li>
                      <strong>{{ $tr('Required for every QSO') }}:</strong>
                      <code>CALL</code>, <code>QSO_DATE</code>,
                      <code>TIME_ON</code>, <code>MODE</code> or
                      <code>SUBMODE</code>, and <code>BAND</code> or
                      <code>FREQ</code>
                    </li>
                    <li
                      v-for="mapping in adifExchangeFieldPreview"
                      :key="mapping.key"
                    >
                      <strong>{{ $tr(mapping.label) }}:</strong>
                      <code v-for="tag in mapping.tags" :key="tag">{{
                        tag
                      }}</code>
                    </li>
                  </ul>
                  <div v-if="categoryDimensions.length" class="adif-dimensions">
                    <strong>{{ $tr('Configured entrant dimensions') }}</strong>
                    <ul>
                      <li
                        v-for="dimension in categoryDimensions"
                        :key="dimension.key"
                      >
                        {{ $tr(dimension.label) }}:
                        {{
                          dimension.choices
                            .map((choice) => $tr(choice.label))
                            .join(', ')
                        }}
                      </li>
                    </ul>
                    <p>
                      {{
                        $tr(
                          'ADIF has no universal entrant-category field. The configured dimension choices are shown here; use the contest’s supported category fields when the logger provides them.',
                        )
                      }}
                    </p>
                  </div>
                </section>
                <p
                  v-if="scoringExamples[String(configured.rule.kind)]"
                  class="rule-example"
                >
                  <strong>{{ $tr('Worked example') }}:</strong>
                  {{ $tr(scoringExamples[String(configured.rule.kind)] ?? '') }}
                  <span>{{
                    $tr('Illustrative only; follow the official contest rules.')
                  }}</span>
                </p>
                <RuleSchemaEditor
                  v-if="
                    !['categories', 'exchange'].includes(
                      String(configured.rule.kind),
                    )
                  "
                  :schema="
                    descriptorFor(String(configured.rule.kind))?.schema ?? {}
                  "
                  :root-schema="
                    descriptorFor(String(configured.rule.kind))?.schema ?? {}
                  "
                  :model-value="configured.rule"
                  :hidden-properties="
                    configured.rule.kind === 'eligibility'
                      ? ['allowed_bands', 'allowed_modes']
                      : configured.rule.kind === 'format_mapping' &&
                          configured.rule.format === 'adif'
                        ? ['header_fields', 'qso_columns', 'category_mappings']
                        : []
                  "
                  :category-dimensions="categoryDimensions"
                  :fact-options="multiplierSourceFacts"
                  :label="`${configured.rule.kind} rule settings`"
                  :path="`rules-${index}`"
                  @update:model-value="updateRule(configured, $event)"
                />
                <CategoryExchangeEditor
                  v-if="
                    configured.rule.kind === 'categories' ||
                    configured.rule.kind === 'exchange'
                  "
                  :kind="configured.rule.kind"
                  :model-value="configured.rule"
                  @update:model-value="updateRule(configured, $event)"
                />
                <template v-if="configured.rule.kind === 'eligibility'">
                  <div class="catalog-rule-group">
                    <label class="catalog-toggle">
                      <input
                        type="checkbox"
                        :checked="Array.isArray(configured.rule.allowed_bands)"
                        @change="
                          setSelectedValues(
                            configured,
                            'allowed_bands',
                            ($event.target as HTMLInputElement).checked
                              ? []
                              : undefined,
                          )
                        "
                      />
                      {{ $tr('Configure allowed bands') }}
                    </label>
                    <EligibilityCatalogEditor
                      v-if="Array.isArray(configured.rule.allowed_bands)"
                      kind="band"
                      :items="
                        operatingCatalog.filter((item) => item.kind === 'band')
                      "
                      :selected="selectedValues(configured, 'allowed_bands')"
                      @update:selected="
                        setSelectedValues(configured, 'allowed_bands', $event)
                      "
                    />
                  </div>
                  <div class="catalog-rule-group">
                    <label class="catalog-toggle">
                      <input
                        type="checkbox"
                        :checked="Array.isArray(configured.rule.allowed_modes)"
                        @change="
                          setSelectedValues(
                            configured,
                            'allowed_modes',
                            ($event.target as HTMLInputElement).checked
                              ? []
                              : undefined,
                          )
                        "
                      />
                      {{ $tr('Configure allowed modes') }}
                    </label>
                    <EligibilityCatalogEditor
                      v-if="Array.isArray(configured.rule.allowed_modes)"
                      kind="mode"
                      :items="
                        operatingCatalog.filter((item) => item.kind === 'mode')
                      "
                      :selected="selectedValues(configured, 'allowed_modes')"
                      @update:selected="
                        setSelectedValues(configured, 'allowed_modes', $event)
                      "
                    />
                  </div>
                </template>
                <details
                  v-if="
                    configured.rule.kind === 'eligibility' ||
                    supportsConditions(configured)
                  "
                  class="advanced-settings"
                >
                  <summary>{{ $tr('Advanced conditions') }}</summary>
                  <div
                    v-if="configured.rule.kind === 'eligibility'"
                    class="condition-toggle"
                  >
                    <label>
                      <input
                        type="checkbox"
                        :checked="Boolean(configured.rule.eligible_if)"
                        @change="
                          setEligibilityCondition(
                            configured,
                            ($event.target as HTMLInputElement).checked
                              ? {
                                  kind: 'compare',
                                  fact: 'qso.entity',
                                  operator: 'eq',
                                  value: 'K',
                                }
                              : undefined,
                          )
                        "
                      />
                      {{
                        $tr(
                          'Require contacts to match an eligibility condition',
                        )
                      }}
                    </label>
                    <p class="field-help">
                      {{
                        $tr(
                          'This controls whether a contact is eligible at all. Use it only for a contact-level restriction in the sponsor’s rules, such as requiring a particular entity. The API reports unsupported facts when you validate.',
                        )
                      }}
                    </p>
                    <ConditionEditor
                      v-if="configured.rule.eligible_if"
                      :model-value="
                        configured.rule.eligible_if as Record<string, unknown>
                      "
                      @update:model-value="
                        setEligibilityCondition(configured, $event)
                      "
                    />
                  </div>
                  <div
                    v-if="supportsConditions(configured)"
                    class="condition-toggle"
                  >
                    <label>
                      <input
                        type="checkbox"
                        :checked="Boolean(configured.when)"
                        @change="
                          setCondition(
                            configured,
                            ($event.target as HTMLInputElement).checked
                              ? {
                                  kind: 'compare',
                                  fact: 'qso.band',
                                  operator: 'eq',
                                  value: '20m',
                                }
                              : undefined,
                          )
                        "
                      />
                      {{ $tr('Apply this rule only when a condition matches') }}
                    </label>
                    <p class="field-help">
                      {{
                        $tr(
                          'This makes the whole rule conditional instead of applying it to every entry or contact. For example, a points or multiplier rule may apply only on a particular band. This is separate from QSO eligibility, which decides whether the contact can count at all.',
                        )
                      }}
                    </p>
                    <ConditionEditor
                      v-if="configured.when"
                      :model-value="configured.when"
                      @update:model-value="setCondition(configured, $event)"
                    />
                  </div>
                </details>
                <details class="advanced-settings">
                  <summary>{{ $tr('Technical details') }}</summary>
                  <label class="rule-id-control">
                    {{ $tr('Rule identifier') }}
                    <input
                      v-model="configured.id"
                      maxlength="80"
                      @input="clearValidation"
                    />
                    <span class="field-help">{{
                      $tr(
                        'A unique lowercase key for this rule inside the ruleset. It helps identify the rule in validation messages and score explanations.',
                      )
                    }}</span>
                  </label>
                </details>
                <button
                  v-if="!descriptorFor(String(configured.rule.kind))?.required"
                  type="button"
                  class="quiet-button remove-rule"
                  @click="removeRule(index)"
                >
                  {{ $tr('Remove rule') }}
                </button>
              </div>
            </details>
          </section>

          <details v-if="currentStep === 5" class="draft-tools">
            <summary>{{ $tr('JSON draft tools') }}</summary>
            <div class="composer-actions">
              <button
                type="button"
                class="secondary-button"
                @click="exportDraft"
              >
                {{ $tr('Download JSON draft') }}
              </button>
              <label id="import-ruleset" class="file-button">
                {{ $tr('Import JSON draft') }}
                <input
                  ref="fileInput"
                  type="file"
                  accept="application/json,.json"
                  @change="importDraft"
                />
              </label>
            </div>
          </details>

          <section
            v-if="currentStep === 5"
            class="review-validation"
            aria-labelledby="validation-result-title"
          >
            <h2 id="validation-result-title">{{ $tr('Validate and save') }}</h2>
            <p>
              {{
                $tr(
                  'The server checks required rules, supported combinations, log mappings, and integer scoring before a version can be saved.',
                )
              }}
            </p>
            <p v-if="issues.length" role="status" class="validation-guidance">
              {{
                $tr(
                  'Validation found a contradiction, incompatibility, or another ruleset error. Fix the listed fields, then validate again before saving.',
                )
              }}
            </p>
            <ul
              v-if="issues.length"
              class="error-list"
              :aria-label="$tr('Ruleset validation errors')"
            >
              <li
                v-for="(issue, index) in issues"
                :key="`${index}-${issue.message}`"
              >
                <span>{{ $tr(displayIssue(issue)) }}</span>
                <button
                  type="button"
                  class="text-button"
                  @click="openValidationIssue(issue)"
                >
                  {{ $tr('Open this section') }}
                </button>
              </li>
            </ul>
            <section
              v-if="validation"
              aria-labelledby="validated-title"
              class="validation-panel"
              role="status"
            >
              <h3 id="validated-title">{{ $tr('Ruleset is valid') }}</h3>
              <pre class="rules-summary">{{ validation.summary }}</pre>
              <div
                v-if="validation.worked_score_example.final_score !== undefined"
                class="example-card"
              >
                <h4>{{ $tr('Worked integer score example') }}</h4>
                <p>
                  {{ $tr('Example inputs:') }}
                  {{
                    JSON.stringify(validation.worked_score_example.variables)
                  }}
                </p>
                <ol>
                  <li
                    v-for="(step, index) in validation.worked_score_example
                      .steps"
                    :key="index"
                  >
                    {{ step.operation }} → {{ step.result }}
                  </li>
                </ol>
              </div>
              <p
                v-else-if="validation.worked_score_example.error"
                class="notice"
              >
                {{ $tr('Formula preview:') }}
                {{ validation.worked_score_example.error }}
              </p>
              <p class="draft-note">
                {{
                  $tr(
                    'Saving creates an immutable version. Existing versions and contest assignments remain unchanged; assign a new version from the contest manager when you are ready.',
                  )
                }}
              </p>
              <button
                type="button"
                class="primary-button"
                :disabled="savingVersion"
                @click="persistDraft"
              >
                {{
                  savingVersion
                    ? $tr('Saving…')
                    : $tr('Save validated ruleset version')
                }}
              </button>
            </section>
          </section>
        </div>

        <aside
          class="draft-overview"
          :aria-label="$tr('Ruleset progress summary')"
        >
          <h2>{{ $tr('Your ruleset so far') }}</h2>
          <p class="draft-overview-note">
            {{
              $tr(
                'Defaults are not sponsor confirmation. Review each section before validation.',
              )
            }}
          </p>
          <ol>
            <li
              v-for="step in STEPS"
              :key="step.number"
              :class="{ 'is-current': currentStep === step.number }"
            >
              <button type="button" @click="goToStep(step.number)">
                <span>{{ $tr(step.title) }}</span>
                <small>{{ stepSummary(step.number) }}</small>
              </button>
            </li>
          </ol>
          <p class="required-rules-note">
            {{
              $tr(
                'Eight required rule types are included. Add optional rules only when the official rules call for them.',
              )
            }}
          </p>
        </aside>
      </div>

      <nav class="step-controls" :aria-label="$tr('Ruleset step navigation')">
        <button
          v-if="currentStep > 1"
          type="button"
          class="secondary-button"
          @click="goToStep(currentStep - 1)"
        >
          {{ $tr('Back') }}
        </button>
        <span>{{ $tr('Step {step} of 5', { step: currentStep }) }}</span>
        <button
          v-if="currentStep < 5"
          type="button"
          class="primary-button"
          @click="goToStep(currentStep + 1)"
        >
          {{ $tr('Continue') }}
        </button>
        <button
          v-else
          type="button"
          class="primary-button"
          :disabled="validating"
          @click="validateDraft"
        >
          {{ validating ? $tr('Validating…') : $tr('Validate ruleset') }}
        </button>
      </nav>
    </template>
    <ResourceAdministrators
      resource-kind="ruleset"
      :resource-id="activeRulesetId"
    />
  </section>
</template>

<style scoped>
.composer-page {
  display: grid;
  gap: 1.2rem;
}
.composer-page .intro {
  margin: 0;
  max-width: 75ch;
  line-height: 1.55;
}
.back-link {
  justify-self: start;
}
.step-navigation {
  overflow-x: auto;
  padding: 0.5rem;
  border: 1px solid var(--color-border);
  border-radius: 0.8rem;
  background: var(--color-surface);
}
.step-navigation ol {
  display: flex;
  min-width: max-content;
  align-items: stretch;
  gap: 0.4rem;
  margin: 0;
  padding: 0;
  list-style: none;
}
.step-navigation button {
  display: flex;
  min-height: 3rem;
  align-items: center;
  gap: 0.55rem;
  padding: 0.45rem 0.7rem;
  border: 1px solid transparent;
  border-radius: 0.55rem;
  color: var(--color-muted);
  background: transparent;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}
.step-navigation button.is-current {
  border-color: var(--color-brand-line);
  color: var(--color-brand-900);
  background: var(--color-brand-wash);
}
.step-number {
  display: grid;
  width: 1.8rem;
  height: 1.8rem;
  flex: 0 0 1.8rem;
  place-items: center;
  border-radius: 50%;
  color: var(--color-brand-900);
  background: var(--color-surface-muted);
  font-size: 0.9rem;
}
.is-current .step-number {
  color: var(--color-surface);
  background: var(--color-brand-700);
}
.step-status {
  margin: -0.65rem 0 0;
  color: var(--color-muted);
  font-size: 0.9rem;
}
.builder-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(16rem, 22rem);
  align-items: start;
  gap: 1rem;
}
.builder-main {
  display: grid;
  min-width: 0;
  gap: 1rem;
}
.step-content h2,
.review-groups h2,
.review-validation h2 {
  margin: 0;
}
.step-description {
  margin: 0.35rem 0 0;
  color: var(--color-muted);
  line-height: 1.5;
}
.review-reminder,
.step-hint {
  padding: 0.75rem 0.9rem;
  border-left: 0.25rem solid var(--color-brand-600);
  border-radius: 0.35rem;
  color: var(--color-muted);
  background: var(--color-brand-wash);
  line-height: 1.45;
}
.review-reminder {
  margin: 0.8rem 0 0;
}
.step-hint {
  margin: 0;
}
.draft-overview {
  position: sticky;
  top: 1rem;
  display: grid;
  gap: 0.75rem;
  padding: 1rem;
  border: 1px solid var(--color-border);
  border-radius: 0.8rem;
  background: var(--color-surface);
  box-shadow: 0 10px 28px var(--color-card-shadow);
}
.draft-overview h2 {
  margin: 0;
  font-size: 1.15rem;
}
.draft-overview-note,
.required-rules-note {
  margin: 0;
  color: var(--color-muted);
  font-size: 0.85rem;
  line-height: 1.45;
}
.draft-overview ol {
  display: grid;
  gap: 0.35rem;
  margin: 0;
  padding: 0;
  list-style: none;
}
.draft-overview li {
  border-left: 3px solid transparent;
  border-radius: 0.35rem;
}
.draft-overview li.is-current {
  border-left-color: var(--color-brand-600);
  background: var(--color-brand-wash);
}
.draft-overview li button {
  display: grid;
  width: 100%;
  gap: 0.2rem;
  padding: 0.55rem 0.65rem;
  border: 0;
  color: var(--color-ink);
  background: transparent;
  text-align: left;
  font: inherit;
  cursor: pointer;
}
.draft-overview li small {
  color: var(--color-muted);
  font-size: 0.78rem;
}
.review-groups {
  display: grid;
  gap: 0.7rem;
}
.review-group {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.9rem 1rem;
  border: 1px solid var(--color-border);
  border-radius: 0.75rem;
  background: var(--color-surface);
}
.review-group h3 {
  margin: 0;
  font-size: 1rem;
}
.review-group p {
  margin: 0.25rem 0 0;
  color: var(--color-muted);
  font-size: 0.9rem;
}
.panel,
.rule-card,
.validation-panel,
.review-validation,
.draft-tools {
  padding: clamp(1rem, 3vw, 1.5rem);
  border: 1px solid var(--color-border);
  border-radius: 0.8rem;
  background: var(--color-surface);
  box-shadow: 0 10px 28px var(--color-card-shadow);
}
.panel legend {
  padding: 0 0.4rem;
  font-weight: 700;
}
.metadata-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 23rem), 1fr));
  align-items: start;
  gap: 1rem;
}
.metadata-grid label,
.rule-id-control,
.add-rule-control label {
  display: grid;
  gap: 0.35rem;
  color: var(--color-brand-900);
  font-weight: 600;
}
.metadata-grid input,
.rule-id-control input,
.add-rule-control select {
  width: 100%;
  min-width: 0;
  min-height: 2.7rem;
  padding: 0.55rem 0.65rem;
  border: 1px solid var(--color-border);
  border-radius: 0.45rem;
  color: var(--color-ink);
  background: var(--color-surface);
  font: inherit;
}
.optional-label {
  color: var(--color-muted);
  font-size: 0.8rem;
  font-weight: 400;
}
.metadata-field-label {
  display: flex;
  align-items: baseline;
  gap: 0.4rem;
}
.section-help,
.field-help {
  display: block;
  max-width: 76ch;
  margin: 0.25rem 0 0;
  color: var(--color-muted);
  font-size: 0.88rem;
  font-weight: 400;
  line-height: 1.45;
}
.section-help {
  margin: 0.3rem 0 0.9rem;
}
.metadata-grid code,
.mutually-exclusive code {
  padding: 0.05rem 0.25rem;
  border-radius: 0.25rem;
  background: var(--color-surface-muted);
}
.rules-section {
  display: grid;
  gap: 0.9rem;
}
.section-heading,
.rule-card-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}
.section-heading {
  flex-wrap: wrap;
}
.section-heading h2,
.rule-card-heading h3 {
  margin: 0;
}
.section-heading p,
.rule-card-heading p {
  margin: 0.3rem 0 0;
  color: var(--color-muted);
}
.add-rule-control {
  display: grid;
  grid-template-columns: minmax(12rem, 1fr) auto;
  align-items: end;
  gap: 0.5rem;
  flex: 1 1 24rem;
  width: min(100%, 38rem);
  max-width: 38rem;
  min-width: min(100%, 24rem);
}
.add-rule-control label {
  min-width: 0;
  display: grid;
  gap: 0.35rem;
  color: var(--color-brand-900);
  font-weight: 600;
}
.add-rule-control .field-help {
  grid-column: 1 / -1;
}
.rule-card {
  padding: 0;
  overflow: clip;
}
.rule-card[open] {
  display: grid;
  gap: 0;
}
.rule-card-heading {
  display: flex;
  min-height: 4rem;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.9rem 1rem;
  color: var(--color-ink);
  cursor: pointer;
  list-style-position: inside;
}
.rule-card-heading::marker {
  color: var(--color-brand-700);
}
.rule-card-title {
  display: grid;
  flex: 1;
  gap: 0.25rem;
}
.rule-card-title small {
  color: var(--color-muted);
  font-size: 0.85rem;
  font-weight: 400;
  line-height: 1.4;
}
.rule-card-body {
  display: grid;
  gap: 1rem;
  padding: 0 1rem 1rem;
}
.rule-id-control {
  width: min(100%, 36rem);
}
.advanced-settings,
.draft-tools {
  border: 1px solid var(--color-border);
  border-radius: 0.6rem;
  background: var(--color-surface);
}
.advanced-settings {
  padding: 0.75rem 0.9rem;
}
.advanced-settings > summary,
.draft-tools > summary {
  color: var(--color-brand-900);
  font-weight: 650;
  cursor: pointer;
}
.advanced-settings[open] > summary {
  margin-bottom: 0.8rem;
}
.draft-tools {
  padding: 0.9rem 1rem;
}
.draft-tools[open] > summary {
  margin-bottom: 0.8rem;
}
.catalog-rule-group {
  display: grid;
  gap: 0.6rem;
  padding: 0.8rem;
  border: 1px solid var(--color-border);
  border-radius: 0.6rem;
  background: var(--color-surface-muted);
}
.catalog-toggle {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  color: var(--color-brand-900);
  font-weight: 650;
}
.catalog-toggle input {
  width: 1.1rem;
  height: 1.1rem;
  accent-color: var(--color-brand-700);
}
.remove-rule {
  justify-self: start;
}
.rule-explanation {
  max-width: 80ch;
  margin: 0;
  padding: 0.75rem 0.9rem;
  border-left: 0.25rem solid var(--color-border-strong);
  color: var(--color-muted);
  background: var(--color-surface-muted);
  line-height: 1.55;
}
.rule-example {
  display: grid;
  gap: 0.25rem;
  max-width: 80ch;
  margin: 0;
  padding: 0.75rem 0.9rem;
  border-left: 0.25rem solid var(--color-brand-600);
  color: var(--color-brand-900);
  background: var(--color-brand-wash);
  line-height: 1.55;
}
.rule-example > span {
  color: var(--color-muted);
  font-size: 0.9rem;
}
.exchange-map-preview {
  max-width: 80ch;
  padding: 0.75rem 0.9rem;
  border-left: 0.25rem solid var(--color-border-strong);
  background: var(--color-surface-muted);
  line-height: 1.5;
}
.exchange-map-preview ul {
  display: grid;
  gap: 0.25rem;
  margin: 0.5rem 0;
  padding-left: 1.25rem;
}
.exchange-map-preview p {
  margin: 0;
  color: var(--color-muted);
}
.adif-dimensions {
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid var(--color-border);
}
.adif-dimensions ul {
  margin: 0.5rem 0;
}
.required-badge {
  padding: 0.3rem 0.55rem;
  border-radius: 999px;
  color: var(--color-success-ink);
  background: var(--color-success-surface);
  font-size: 0.8rem;
}
.condition-toggle {
  display: grid;
  gap: 0.8rem;
}
.condition-toggle > label {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  color: var(--color-brand-900);
}
.condition-toggle input[type='checkbox'] {
  width: 1.1rem;
  height: 1.1rem;
  accent-color: var(--color-brand-700);
}
.review-validation {
  display: grid;
  gap: 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: 0.8rem;
  background: var(--color-surface);
}
.review-validation > p {
  margin: 0;
  color: var(--color-muted);
  line-height: 1.5;
}
.error-list li {
  display: grid;
  gap: 0.5rem;
}
.text-button {
  justify-self: start;
  padding: 0;
  border: 0;
  color: var(--color-brand-700);
  background: transparent;
  font: inherit;
  font-weight: 650;
  text-decoration: underline;
  cursor: pointer;
}
.step-controls {
  position: sticky;
  bottom: 0;
  z-index: 2;
  display: flex;
  min-height: 4rem;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.55rem 0.8rem;
  border: 1px solid var(--color-border);
  border-radius: 0.75rem;
  background: color-mix(in srgb, var(--color-surface) 94%, transparent);
  box-shadow: 0 -6px 20px var(--color-card-shadow);
}
.step-controls > span {
  margin-inline: auto;
  color: var(--color-muted);
  font-size: 0.9rem;
}
.composer-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.65rem;
}
.primary-button,
.secondary-button,
.file-button {
  display: inline-flex;
  min-height: 2.7rem;
  align-items: center;
  justify-content: center;
  padding: 0.55rem 0.85rem;
  border: 1px solid var(--color-border-strong);
  border-radius: 0.5rem;
  color: var(--color-brand-900);
  background: var(--color-surface);
  font: inherit;
  font-weight: 650;
  cursor: pointer;
}
.primary-button {
  border-color: var(--color-brand-700);
  color: var(--color-surface);
  background: var(--color-brand-700);
}
.primary-button:disabled {
  cursor: wait;
  opacity: 0.7;
}
.file-button input {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  clip-path: inset(50%);
}
.validation-panel h3 {
  margin-top: 0;
  color: var(--color-success-ink);
}
.rules-summary {
  overflow-x: auto;
  padding: 1rem;
  border-radius: 0.55rem;
  color: var(--color-brand-900);
  background: var(--color-surface-muted);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  line-height: 1.55;
  white-space: pre-wrap;
}
.example-card {
  padding: 0.8rem 1rem;
  border-left: 4px solid var(--color-brand-600);
  background: var(--color-surface-muted);
}
.example-card h4 {
  margin-top: 0;
}
.example-card li {
  margin: 0.35rem 0;
  font-variant-numeric: tabular-nums;
}
.draft-note {
  color: var(--color-muted);
  font-size: 0.9rem;
}
.notice,
.error-panel,
.error-list {
  padding: 0.85rem 1rem;
  border-radius: 0.55rem;
  background: var(--color-surface-muted);
}
.error-panel,
.error-list {
  color: var(--color-error-ink);
  background: var(--color-error-surface);
}
.error-list li + li {
  margin-top: 0.35rem;
}
@media (max-width: 760px) {
  .builder-layout {
    grid-template-columns: minmax(0, 1fr);
  }
  .draft-overview {
    position: static;
    grid-row: 1;
  }
  .draft-overview ol {
    grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr));
  }
  .review-group {
    align-items: flex-start;
    flex-direction: column;
  }
  .section-heading,
  .rule-card-heading {
    flex-direction: column;
    align-items: stretch;
  }
  .rule-card-heading {
    flex-direction: row;
    align-items: center;
  }
  .add-rule-control {
    grid-template-columns: minmax(0, 1fr);
    min-width: 0;
  }
  .add-rule-control .field-help {
    grid-column: auto;
  }
  .step-controls {
    margin-inline: -0.25rem;
  }
}
</style>
