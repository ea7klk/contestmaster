import { apiRequest } from './client'
import type { RulesetDraft } from './rulesets'

export type ContestStatus = 'draft' | 'open' | 'closed' | 'published'

export interface ContestPeriodicity {
  frequency: 'annual_date' | 'nth_weekday' | 'first_full_weekend'
  month: number
  day?: number
  weekday?: number
  occurrence?: number
}

export interface Contest {
  id: number
  owner_user_id: number
  name: string
  slug: string
  description: string | null
  starts_at: string
  ends_at: string
  periodicity: ContestPeriodicity | null
  log_submission_cutoff_at: string
  status: ContestStatus
  auto_recalculate_on_upload: boolean
  ruleset_version_id: number | null
  created_at: string
  updated_at: string
}

export interface ContestDraft {
  name: string
  slug: string
  description: string | null
  starts_at: string
  ends_at: string
  periodicity: ContestPeriodicity | null
  log_submission_cutoff_at: string
  auto_recalculate_on_upload: boolean
}

export interface ContestImportPackage {
  contest: ContestDraft
  ruleset: RulesetDraft
}

export interface ContestList {
  items: Contest[]
  meta: { page: number; page_size: number; total: number; pages: number }
}

export function listContests(signal?: AbortSignal) {
  return apiRequest<ContestList>(
    '/contests?page=1&page_size=100&sort=starts_at&order=desc',
    {
      method: 'GET',
      signal,
    },
  )
}

export function createContest(draft: ContestDraft) {
  return apiRequest<Contest>('/contests', {
    method: 'POST',
    body: JSON.stringify(draft),
  })
}

export function importContest(contestPackage: ContestImportPackage) {
  return apiRequest<{ contest: Contest; ruleset_version_id: number }>(
    '/contests/import',
    {
      method: 'POST',
      body: JSON.stringify(contestPackage),
    },
  )
}

export function updateContest(id: number, draft: ContestDraft) {
  return apiRequest<Contest>(`/contests/${id}`, {
    method: 'PUT',
    body: JSON.stringify(draft),
  })
}

export function previewContestSchedule(
  periodicity: ContestPeriodicity,
  year: number,
  starts_at: string,
  ends_at: string,
) {
  return apiRequest<{ starts_at: string; ends_at: string }>(
    '/contests/schedule-preview',
    {
      method: 'POST',
      body: JSON.stringify({ periodicity, year, starts_at, ends_at }),
    },
  )
}

export function selectRuleset(id: number, rulesetVersionId: number) {
  return apiRequest<Contest>(`/contests/${id}/ruleset`, {
    method: 'PUT',
    body: JSON.stringify({ ruleset_version_id: rulesetVersionId }),
  })
}

export function changeContestStatus(id: number, status: ContestStatus) {
  return apiRequest<Contest>(`/contests/${id}/status`, {
    method: 'PUT',
    body: JSON.stringify({ status }),
  })
}
