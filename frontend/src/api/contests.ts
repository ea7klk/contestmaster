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
  ruleset?: RulesetDraft
}

export interface ContestList {
  items: Contest[]
  meta: { page: number; page_size: number; total: number; pages: number }
}

export function listContests(
  page = 1,
  pageSize = 20,
  query = '',
  signal?: AbortSignal,
) {
  const search = query.trim()
  return apiRequest<ContestList>(
    `/contests?page=${page}&page_size=${pageSize}&sort=starts_at&order=desc${search ? `&q=${encodeURIComponent(search)}` : ''}`,
    {
      method: 'GET',
      signal,
    },
  )
}

export function getContest(id: number, signal?: AbortSignal) {
  return apiRequest<Contest>(`/contests/${id}`, { method: 'GET', signal })
}

export function createContest(draft: ContestDraft) {
  return apiRequest<Contest>('/contests', {
    method: 'POST',
    body: JSON.stringify(draft),
  })
}

export function importContest(contestPackage: ContestImportPackage) {
  return apiRequest<{ contest: Contest; ruleset_version_id: number | null }>(
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

export function deleteContest(id: number, confirmSlug: string) {
  return apiRequest<void>(`/contests/${id}`, {
    method: 'DELETE',
    body: JSON.stringify({ confirm_slug: confirmSlug }),
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
