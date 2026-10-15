export interface JsonSchema {
  $defs?: Record<string, JsonSchema>
  $ref?: string
  additionalProperties?: boolean | JsonSchema
  anyOf?: JsonSchema[]
  const?: unknown
  default?: unknown
  description?: string
  enum?: unknown[]
  format?: string
  items?: JsonSchema
  maxItems?: number
  maxLength?: number
  maximum?: number
  minimum?: number
  minItems?: number
  properties?: Record<string, JsonSchema>
  patternProperties?: Record<string, JsonSchema>
  required?: string[]
  title?: string
  type?: string | string[]
}

export interface RuleTypeDescriptor {
  key: string
  label: string
  description: string
  execution: string
  required: boolean
  schema: JsonSchema
}

export interface RuleCatalogResponse {
  rule_types: RuleTypeDescriptor[]
}

export interface RulesetDraft {
  schema_version: 1
  ruleset_key: string
  version: string
  source_url?: string
  source_edition?: string
  rules: Array<{
    id: string
    rule: Record<string, unknown>
    when?: Record<string, unknown>
  }>
}

export interface RulesetIssue {
  location: Array<string | number>
  message: string
  type: string
}

export interface RulesetValidationResponse {
  valid: true
  ruleset_key: string
  version: string
  rule_types: string[]
  summary: string
  worked_score_example: {
    variables?: Record<string, number>
    steps?: Array<{ operation: string; result: number }>
    final_score?: number
    error?: string
  }
}

export class RulesetApiError extends Error {
  readonly issues: RulesetIssue[]

  constructor(message: string, issues: RulesetIssue[] = []) {
    super(message)
    this.name = 'RulesetApiError'
    this.issues = issues
  }
}

const apiPrefix = import.meta.env.VITE_API_PREFIX ?? '/api/v1'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${apiPrefix}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
  } catch {
    throw new RulesetApiError(
      'The API could not be reached. Check the connection and try again.',
    )
  }

  const payload = (await response.json().catch(() => null)) as
    { error?: { message?: string; details?: RulesetIssue[] } } | T | null
  if (!response.ok) {
    const error =
      payload !== null && typeof payload === 'object' && 'error' in payload
        ? (
            payload as {
              error?: { message?: string; details?: RulesetIssue[] }
            }
          ).error
        : undefined
    throw new RulesetApiError(
      error?.message ?? `The API returned HTTP ${response.status}.`,
      error?.details ?? [],
    )
  }
  return payload as T
}

export function getRuleCatalog(
  signal?: AbortSignal,
): Promise<RuleCatalogResponse> {
  return request<RuleCatalogResponse>('/rulesets/catalog', {
    method: 'GET',
    signal,
  })
}

export function validateRuleset(
  draft: RulesetDraft,
  signal?: AbortSignal,
): Promise<RulesetValidationResponse> {
  return request<RulesetValidationResponse>('/rulesets/validate', {
    method: 'POST',
    body: JSON.stringify(draft),
    signal,
  })
}
