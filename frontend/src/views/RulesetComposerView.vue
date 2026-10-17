<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import ConditionEditor from '../components/ConditionEditor.vue'
import RuleSchemaEditor from '../components/RuleSchemaEditor.vue'
import CategoryExchangeEditor from '../components/CategoryExchangeEditor.vue'
import EligibilityCatalogEditor from '../components/EligibilityCatalogEditor.vue'
import ResourceAdministrators from '../components/ResourceAdministrators.vue'
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

const optionalTypes = computed(() =>
  catalog.value.filter((type) => !type.required),
)
const usedSingletonKinds = computed(
  () => new Set(rules.value.map((item) => String(item.rule.kind))),
)
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
  return {
    id: `${kind.replaceAll('_', '-')}-${idNumber}`,
    rule: initialValue(descriptor.schema, descriptor.schema) as Record<
      string,
      unknown
    >,
  }
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
  rule.rule = value as Record<string, unknown>
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
  rules.value = definition.rules.map((item) => ({ ...item }))
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
    rules.value = normalizedRules.map((item) => ({ ...item }))
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
    <a class="secondary-button" href="/manage/rulesets">{{
      $tr('← Back to rulesets')
    }}</a>

    <section class="workflow-guide" aria-labelledby="workflow-title">
      <h2 id="workflow-title">{{ $tr('How to create a ruleset') }}</h2>
      <ol>
        <li>
          <strong>{{ $tr('Start from the published rules.') }}</strong>
          {{
            $tr(
              'Use the rules URL and edition below so the configuration can be traced to its source.',
            )
          }}
        </li>
        <li>
          <strong>{{ $tr('Configure the required rule types.') }}</strong>
          {{
            $tr(
              'These provide the basic entry categories, exchange, contact eligibility, duplicate handling, point calculation, and accepted log format.',
            )
          }}
        </li>
        <li>
          <strong>{{
            $tr('Add optional rule types only when needed.')
          }}</strong>
          {{
            $tr(
              'Add multipliers, bonuses, penalties, operating constraints, or workflow steps only when the sponsor’s rules define them. Use each section’s help to translate that rule into settings.',
            )
          }}
        </li>
        <li>
          <strong>{{ $tr('Validate, then save and assign.') }}</strong>
          {{
            $tr(
              'Fix any field errors, review the generated summary and example, and save a new immutable version. Assign that version to a contest from the contest manager.',
            )
          }}
        </li>
      </ol>
      <p>
        {{
          $tr(
            'Event dates, recurrence, and the UTC log-submission cutoff belong to the contest configuration. A ruleset can be reused by contests with different dates; its submission rule only defines late-log handling. If a sponsor requirement cannot be expressed by the available settings, do not approximate it with a different rule; record the gap for review.',
          )
        }}
      </p>
    </section>

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
      <fieldset class="panel metadata-panel">
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
            <span class="metadata-field-label">{{ $tr('Ruleset key') }}</span>
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

      <section aria-labelledby="configured-rules-title" class="rules-section">
        <div class="section-heading">
          <div>
            <h2 id="configured-rules-title">
              {{ $tr('Configured rule types') }}
            </h2>
            <p>
              {{
                $tr(
                  'Required sections form the built-in baseline and cannot be removed. Configure their values to match the sponsor’s rules; optional sections add other supported behavior.',
                )
              }}
            </p>
          </div>
          <div class="add-rule-control">
            <label for="add-rule-type"
              >{{ $tr('Add an optional rule type') }}
              <select id="add-rule-type" v-model="selectedType">
                <option value="">{{ $tr('Choose a rule type') }}</option>
                <option
                  v-for="type in optionalTypes"
                  :key="type.key"
                  :value="type.key"
                  :disabled="
                    [
                      'submission',
                      'categories',
                      'format_mapping',
                      'score_formula',
                    ].includes(type.key) && usedSingletonKinds.has(type.key)
                  "
                >
                  {{ type.label }}
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
            <p class="field-help">
              {{
                $tr(
                  'Choose a supported optional rule type, then add it. You can add repeatable types more than once and remove an optional rule that does not apply.',
                )
              }}
            </p>
          </div>
        </div>

        <article
          v-for="(configured, index) in rules"
          :key="configured.id"
          class="rule-card"
        >
          <div class="rule-card-heading">
            <div>
              <h3>
                {{
                  $tr(
                    String(
                      descriptorFor(String(configured.rule.kind))?.label ??
                        configured.rule.kind,
                    ),
                  )
                }}
              </h3>
              <p>
                {{
                  $tr(
                    descriptorFor(String(configured.rule.kind))?.description ??
                      '',
                  )
                }}
              </p>
            </div>
            <button
              v-if="!descriptorFor(String(configured.rule.kind))?.required"
              type="button"
              class="quiet-button"
              @click="removeRule(index)"
            >
              {{ $tr('Remove rule') }}
            </button>
            <span v-else class="required-badge">{{ $tr('Required') }}</span>
          </div>
          <label class="rule-id-control">
            {{ $tr('Rule identifier') }}
            <input
              v-model="configured.id"
              maxlength="80"
              @input="clearValidation"
            />
            <span class="field-help">
              {{
                $tr(
                  'A unique lowercase key for this rule inside the ruleset. It helps identify the rule in validation messages and score explanations.',
                )
              }}
            </span>
          </label>
          <RuleSchemaEditor
            v-if="
              !['categories', 'exchange'].includes(String(configured.rule.kind))
            "
            :schema="descriptorFor(String(configured.rule.kind))?.schema ?? {}"
            :root-schema="
              descriptorFor(String(configured.rule.kind))?.schema ?? {}
            "
            :model-value="configured.rule"
            :hidden-properties="
              configured.rule.kind === 'eligibility'
                ? ['allowed_bands', 'allowed_modes']
                : []
            "
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
          <p
            v-if="helpText[String(configured.rule.kind)]"
            class="rule-explanation"
          >
            {{ $tr(helpText[String(configured.rule.kind)] ?? '') }}
          </p>
          <template v-if="configured.rule.kind === 'eligibility'">
            <label
              ><input
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
              {{ $tr('Configure allowed bands') }}</label
            >
            <EligibilityCatalogEditor
              v-if="Array.isArray(configured.rule.allowed_bands)"
              kind="band"
              :items="operatingCatalog.filter((item) => item.kind === 'band')"
              :selected="selectedValues(configured, 'allowed_bands')"
              @update:selected="
                setSelectedValues(configured, 'allowed_bands', $event)
              "
            />
            <label
              ><input
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
              {{ $tr('Configure allowed modes') }}</label
            >
            <EligibilityCatalogEditor
              v-if="Array.isArray(configured.rule.allowed_modes)"
              kind="mode"
              :items="operatingCatalog.filter((item) => item.kind === 'mode')"
              :selected="selectedValues(configured, 'allowed_modes')"
              @update:selected="
                setSelectedValues(configured, 'allowed_modes', $event)
              "
            />
          </template>
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
              {{ $tr('Require contacts to match an eligibility condition') }}
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
              @update:model-value="setEligibilityCondition(configured, $event)"
            />
          </div>
          <div v-if="supportsConditions(configured)" class="condition-toggle">
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
        </article>
      </section>

      <div class="composer-actions">
        <button
          type="button"
          class="primary-button"
          :disabled="validating"
          @click="validateDraft"
        >
          {{ validating ? 'Validating…' : 'Validate ruleset' }}
        </button>
        <button type="button" class="secondary-button" @click="exportDraft">
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

      <ul
        v-if="issues.length"
        class="error-list"
        :aria-label="$tr('Ruleset validation errors')"
      >
        <li v-for="(issue, index) in issues" :key="`${index}-${issue.message}`">
          {{ $tr(displayIssue(issue)) }}
        </li>
      </ul>
      <section
        v-if="validation"
        aria-labelledby="validation-result-title"
        class="validation-panel"
        role="status"
      >
        <h2 id="validation-result-title">{{ $tr('Ruleset is valid') }}</h2>
        <pre class="rules-summary">{{ validation.summary }}</pre>
        <div
          v-if="validation.worked_score_example.final_score !== undefined"
          class="example-card"
        >
          <h3>{{ $tr('Worked integer score example') }}</h3>
          <p>
            {{ $tr('Example inputs:') }}
            {{ JSON.stringify(validation.worked_score_example.variables) }}
          </p>
          <ol>
            <li
              v-for="(step, index) in validation.worked_score_example.steps"
              :key="index"
            >
              {{ step.operation }} → {{ step.result }}
            </li>
          </ol>
        </div>
        <p v-else-if="validation.worked_score_example.error" class="notice">
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
          {{ savingVersion ? 'Saving…' : 'Save validated ruleset version' }}
        </button>
      </section>
    </template>
    <ResourceAdministrators resource-kind="ruleset" :resource-id="activeRulesetId" />
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
.workflow-guide {
  padding: 1rem 1.25rem;
  border-left: 0.35rem solid var(--color-brand-600);
  border-radius: 0.65rem;
  background: var(--color-surface-muted);
}
.workflow-guide h2 {
  margin: 0 0 0.6rem;
}
.workflow-guide ol {
  display: grid;
  gap: 0.55rem;
  margin: 0;
  padding-left: 1.4rem;
}
.workflow-guide li {
  padding-left: 0.2rem;
  line-height: 1.5;
}
.workflow-guide p {
  max-width: 78ch;
  margin: 0.9rem 0 0;
  color: var(--color-muted);
  line-height: 1.5;
}
.panel,
.rule-card,
.validation-panel {
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
  display: grid;
  gap: 1rem;
}
.rule-card-heading {
  align-items: center;
}
.rule-id-control {
  width: min(100%, 36rem);
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
.validation-panel h2 {
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
.example-card h3 {
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
  .section-heading,
  .rule-card-heading {
    flex-direction: column;
    align-items: stretch;
  }
  .add-rule-control {
    grid-template-columns: minmax(0, 1fr);
    min-width: 0;
  }
  .add-rule-control .field-help {
    grid-column: auto;
  }
}
</style>
