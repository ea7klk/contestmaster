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
  schema_version: 2
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

export type RulesetIssue = ApiIssue

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

export class RulesetApiError extends ApiError {
  constructor(message: string, issues: RulesetIssue[] = []) {
    super(message, issues)
    this.name = 'RulesetApiError'
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  try {
    return await apiRequest<T>(path, init)
  } catch (error) {
    if (error instanceof ApiError) {
      throw new RulesetApiError(error.message, error.issues)
    }
    throw error
  }
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
export interface SavedRulesetVersion {
  id: number
  ruleset_key: string
  version: string
  source_url: string | null
  source_edition: string | null
  rule_type_keys: string[]
  created_by_user_id: number | null
  created_at: string
  can_delete: boolean
}

export async function listRulesetVersions(
  signal?: AbortSignal,
): Promise<{ items: SavedRulesetVersion[] }> {
  return request('/rulesets/versions', { method: 'GET', signal })
}

export async function getSavedRulesetVersion(
  id: number,
  signal?: AbortSignal,
): Promise<{ id: number; configuration: RulesetDraft }> {
  return request(`/rulesets/versions/${id}`, { method: 'GET', signal })
}

export async function saveRulesetVersion(
  draft: RulesetDraft,
  signal?: AbortSignal,
): Promise<SavedRulesetVersion & { created: boolean }> {
  return request('/rulesets/versions', {
    method: 'POST',
    body: JSON.stringify(draft),
    signal,
  })
}

export function deleteSavedRulesetVersion(id: number, confirmIdentity: string) {
  return request<void>(`/rulesets/versions/${id}`, {
    method: 'DELETE',
    body: JSON.stringify({ confirm_identity: confirmIdentity }),
  })
}

import { ApiError, apiRequest, type ApiIssue } from './client'
