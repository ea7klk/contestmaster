import { apiRequest } from './client'
import type { RulesetDraft } from './rulesets'

export type ContestStatus = 'draft' | 'open' | 'closed' | 'published'

export interface ContestPeriodicity {
  frequency:
    | 'annual_date'
    | 'nth_weekday'
    | 'first_full_weekend'
    | 'last_full_weekend'
    | 'nth_full_weekend'
  month: number | number[]
  day?: number
  weekday?: number | number[]
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
  cutoff_is_override?: boolean
  series_id?: number | null
  series_occurrence_date?: string | null
  is_series_anchor?: boolean
  series_cutoff_offset_seconds?: number | null
  series_automatic_window_days?: number | null
  series_edition_count?: number | null
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
  cutoff_offset_seconds?: number | null
  cutoff_is_override?: boolean
  automatic_window_days?: number | null
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
  starts_at: string,
  ends_at: string,
  exceptions: ContestSeriesException[] = [],
) {
  return apiRequest<{
    starts_at: string
    ends_at: string
    occurrences?: Array<{ starts_at: string; ends_at: string }>
  }>('/contests/schedule-preview', {
    method: 'POST',
    body: JSON.stringify({ periodicity, starts_at, ends_at, exceptions }),
  })
}

export interface ContestSeriesException {
  occurrence_date: string
  action: 'skip' | 'move'
  moved_to_date: string | null
}

export function listSeriesExceptions(seriesId: number) {
  return apiRequest<{ items: ContestSeriesException[] }>(
    `/contests/series/${seriesId}/exceptions`,
    { method: 'GET' },
  )
}

export function setSeriesException(
  seriesId: number,
  exception: ContestSeriesException,
) {
  return apiRequest<ContestSeriesException>(
    `/contests/series/${seriesId}/exceptions`,
    { method: 'POST', body: JSON.stringify(exception) },
  )
}

export function removeSeriesException(
  seriesId: number,
  occurrenceDate: string,
) {
  return apiRequest<void>(
    `/contests/series/${seriesId}/exceptions/${occurrenceDate}`,
    { method: 'DELETE' },
  )
}

export function deleteContestSeries(seriesId: number, confirmName: string) {
  return apiRequest<void>(`/contests/series/${seriesId}`, {
    method: 'DELETE',
    body: JSON.stringify({ confirm_name: confirmName }),
  })
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
