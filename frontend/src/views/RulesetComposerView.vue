<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import ConditionEditor from '../components/ConditionEditor.vue'
import RuleSchemaEditor from '../components/RuleSchemaEditor.vue'
import {
  getRuleCatalog,
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
    [
      'schedule',
      'submission',
      'categories',
      'format_mapping',
      'score_formula',
    ].includes(selectedType.value) &&
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
    'schedule',
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

function buildDraft(): RulesetDraft {
  const draft: RulesetDraft = {
    schema_version: 1,
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
  savingVersion.value = true
  generalError.value = ''
  savedMessage.value = ''
  try {
    const persisted = await saveRulesetVersion(buildDraft())
    savedMessage.value = persisted.created
      ? `Saved ${persisted.ruleset_key} version ${persisted.version}. Assign it from the contest manager.`
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

async function importDraft(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  clearValidation()
  generalError.value = ''
  try {
    const parsed = JSON.parse(await file.text()) as RulesetDraft
    if (
      !Array.isArray(parsed.rules) ||
      typeof parsed.ruleset_key !== 'string'
    ) {
      throw new Error('This file does not look like a ruleset draft.')
    }
    rulesetKey.value = parsed.ruleset_key
    version.value = parsed.version
    sourceUrl.value = parsed.source_url ?? ''
    sourceEdition.value = parsed.source_edition ?? ''
    rules.value = parsed.rules.map((item) => ({ ...item }))
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
    const response = await getRuleCatalog(controller.signal)
    catalog.value = response.rule_types
    seedRequiredRules()
  } catch (error) {
    generalError.value =
      error instanceof Error
        ? error.message
        : 'The rule catalog could not be loaded.'
  } finally {
    catalogLoading.value = false
  }
})
</script>

<template>
  <section class="composer-page" aria-labelledby="composer-title">
    <p class="eyebrow">Contest manager tools</p>
    <h1 id="composer-title">Ruleset composer</h1>
    <p class="intro">
      Build a declarative contest ruleset by adding rule types and configuring
      their fields. The API checks the draft and shows a readable summary and
      integer scoring example.
    </p>

    <p v-if="catalogLoading" role="status" class="notice">
      Loading the built-in rule catalog…
    </p>
    <template v-else-if="catalog.length">
      <fieldset class="panel metadata-panel">
        <legend>Ruleset identity</legend>
        <div class="metadata-grid">
          <label>
            Ruleset key
            <input
              v-model="rulesetKey"
              maxlength="120"
              autocomplete="off"
              @input="clearValidation"
            />
          </label>
          <label>
            Version
            <input
              v-model="version"
              maxlength="80"
              autocomplete="off"
              @input="clearValidation"
            />
          </label>
          <label>
            Published rules URL <span class="optional-label">Optional</span>
            <input
              v-model="sourceUrl"
              type="url"
              maxlength="2048"
              autocomplete="url"
              @input="clearValidation"
            />
          </label>
          <label>
            Source edition or year <span class="optional-label">Optional</span>
            <input
              v-model="sourceEdition"
              maxlength="120"
              @input="clearValidation"
            />
          </label>
        </div>
      </fieldset>

      <section aria-labelledby="configured-rules-title" class="rules-section">
        <div class="section-heading">
          <div>
            <h2 id="configured-rules-title">Configured rule types</h2>
            <p>Rules marked required are needed for a valid initial ruleset.</p>
          </div>
          <div class="add-rule-control">
            <label for="add-rule-type">Add a rule type</label>
            <select id="add-rule-type" v-model="selectedType">
              <option value="">Choose a rule type</option>
              <option
                v-for="type in optionalTypes"
                :key="type.key"
                :value="type.key"
                :disabled="
                  [
                    'schedule',
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
            <button
              type="button"
              class="secondary-button"
              :disabled="!selectedType"
              @click="addSelectedRule"
            >
              Add rule
            </button>
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
                  descriptorFor(String(configured.rule.kind))?.label ??
                  configured.rule.kind
                }}
              </h3>
              <p>
                {{ descriptorFor(String(configured.rule.kind))?.description }}
              </p>
            </div>
            <button
              v-if="!descriptorFor(String(configured.rule.kind))?.required"
              type="button"
              class="quiet-button"
              @click="removeRule(index)"
            >
              Remove rule
            </button>
            <span v-else class="required-badge">Required</span>
          </div>
          <label class="rule-id-control">
            Rule identifier
            <input
              v-model="configured.id"
              maxlength="80"
              @input="clearValidation"
            />
          </label>
          <RuleSchemaEditor
            :schema="descriptorFor(String(configured.rule.kind))?.schema ?? {}"
            :root-schema="
              descriptorFor(String(configured.rule.kind))?.schema ?? {}
            "
            :model-value="configured.rule"
            :label="`${configured.rule.kind} rule settings`"
            :path="`rules-${index}`"
            @update:model-value="updateRule(configured, $event)"
          />
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
              Require contacts to match an eligibility condition
            </label>
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
              Apply this rule only when a condition matches
            </label>
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
          Download JSON draft
        </button>
        <label class="file-button">
          Import JSON draft
          <input
            ref="fileInput"
            type="file"
            accept="application/json,.json"
            @change="importDraft"
          />
        </label>
      </div>

      <p v-if="generalError" role="alert" class="error-panel">
        {{ generalError }}
      </p>
      <ul
        v-if="issues.length"
        class="error-list"
        aria-label="Ruleset validation errors"
      >
        <li v-for="(issue, index) in issues" :key="`${index}-${issue.message}`">
          {{ displayIssue(issue) }}
        </li>
      </ul>
      <section
        v-if="validation"
        aria-labelledby="validation-result-title"
        class="validation-panel"
        role="status"
      >
        <h2 id="validation-result-title">Ruleset is valid</h2>
        <pre class="rules-summary">{{ validation.summary }}</pre>
        <div
          v-if="validation.worked_score_example.final_score !== undefined"
          class="example-card"
        >
          <h3>Worked integer score example</h3>
          <p>
            Example inputs:
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
          Formula preview: {{ validation.worked_score_example.error }}
        </p>
        <p class="draft-note">
          Saving creates an immutable version. Assign it to one of your draft
          contests from the contest manager.
        </p>
        <button
          type="button"
          class="primary-button"
          :disabled="savingVersion"
          @click="persistDraft"
        >
          {{ savingVersion ? 'Saving…' : 'Save validated ruleset version' }}
        </button>
        <p v-if="savedMessage" role="status" class="notice">
          {{ savedMessage }}
        </p>
      </section>
    </template>
  </section>
</template>

<style scoped>
.composer-page {
  display: grid;
  gap: 1.2rem;
}
.composer-page .intro {
  margin: 0;
}
.panel,
.rule-card,
.validation-panel {
  padding: clamp(1rem, 3vw, 1.5rem);
  border: 1px solid #d4e0e5;
  border-radius: 0.8rem;
  background: #fff;
  box-shadow: 0 10px 28px #18394e08;
}
.panel legend {
  padding: 0 0.4rem;
  font-weight: 700;
}
.metadata-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}
.metadata-grid label,
.rule-id-control,
.add-rule-control label {
  display: grid;
  gap: 0.35rem;
  color: #314b5a;
  font-weight: 600;
}
.metadata-grid input,
.rule-id-control input,
.add-rule-control select {
  min-height: 2.7rem;
  padding: 0.55rem 0.65rem;
  border: 1px solid #b9c8d0;
  border-radius: 0.45rem;
  color: #192a3a;
  background: #fff;
  font: inherit;
}
.optional-label {
  color: #647a86;
  font-size: 0.8rem;
  font-weight: 400;
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
.section-heading h2,
.rule-card-heading h3 {
  margin: 0;
}
.section-heading p,
.rule-card-heading p {
  margin: 0.3rem 0 0;
  color: #596f7b;
}
.add-rule-control {
  display: flex;
  align-items: end;
  gap: 0.5rem;
}
.add-rule-control label {
  min-width: 12rem;
}
.rule-card {
  display: grid;
  gap: 1rem;
}
.rule-card-heading {
  align-items: center;
}
.rule-id-control {
  max-width: 22rem;
}
.required-badge {
  padding: 0.3rem 0.55rem;
  border-radius: 999px;
  color: #23573d;
  background: #e8f5ed;
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
  color: #344e5d;
}
.condition-toggle input[type='checkbox'] {
  width: 1.1rem;
  height: 1.1rem;
  accent-color: #075a83;
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
  border: 1px solid #aabdc7;
  border-radius: 0.5rem;
  color: #16435b;
  background: #fff;
  font: inherit;
  font-weight: 650;
  cursor: pointer;
}
.primary-button {
  border-color: #075a83;
  color: #fff;
  background: #075a83;
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
  color: #23573d;
}
.rules-summary {
  overflow-x: auto;
  padding: 1rem;
  border-radius: 0.55rem;
  color: #213946;
  background: #f3f7f9;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  line-height: 1.55;
  white-space: pre-wrap;
}
.example-card {
  padding: 0.8rem 1rem;
  border-left: 4px solid #11718f;
  background: #f5fafc;
}
.example-card h3 {
  margin-top: 0;
}
.example-card li {
  margin: 0.35rem 0;
  font-variant-numeric: tabular-nums;
}
.draft-note {
  color: #596f7b;
  font-size: 0.9rem;
}
.notice,
.error-panel,
.error-list {
  padding: 0.85rem 1rem;
  border-radius: 0.55rem;
  background: #f3f7f9;
}
.error-panel,
.error-list {
  color: #842b2b;
  background: #fff1f1;
}
.error-list li + li {
  margin-top: 0.35rem;
}
@media (max-width: 760px) {
  .metadata-grid {
    grid-template-columns: 1fr;
  }
  .section-heading,
  .rule-card-heading {
    flex-direction: column;
    align-items: stretch;
  }
  .add-rule-control {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
