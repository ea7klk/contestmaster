import { apiRequest } from './client'
import type { RulesetDraft } from './rulesets'

export interface PublicContest {
  id: number
  name: string
  slug: string
  description: string | null
  starts_at: string
  ends_at: string
  log_submission_cutoff_at: string
  status: string
}

export interface PublicContestDetails extends PublicContest {
  ruleset: RulesetDraft | null
}

export interface PublicContestList {
  items: PublicContest[]
  meta: { page: number; page_size: number; total: number; pages: number }
}

export interface UpcomingContestList extends PublicContestList {
  /** UTC instant used by the API to include future and currently running contests. */
  as_of: string
}

export interface ResultExplanation {
  format_version: number
  points: number
  multipliers: number
  multiplier_counts?: Record<string, number>
  bonus_points: number
  penalty_points: number
  score: number
  qso_count: number
  credited_qso_count: number
  summary: string
}

export interface PublicResultRow {
  id: number
  callsign: string
  category_values: Record<string, string>
  status: string
  score: number
  points: number
  multiplier_count: number
  bonus_points: number
  penalty_points: number
  qso_count: number
  credited_qso_count: number
  placement: number | null
  explanation: ResultExplanation
}

export interface PublicResultsPage {
  contest: {
    id: number
    name: string
    slug: string
    description: string | null
    starts_at: string
    ends_at: string
    status: 'published'
    publication: {
      number: number
      published_at: string
      source_digest: string
      entry_count: number
      withheld_count: number
    }
  }
  items: PublicResultRow[]
  filters: {
    categories: Array<{ key: string; values: string[] }>
    bands: string[]
    modes: string[]
    statuses: string[]
  }
  meta: { page: number; page_size: number; total: number; pages: number }
}

export interface ManagerResultCandidate {
  entry_id: number
  entry_status: string
  is_late: boolean
  revision_id: number
  revision_number: number
  score_run_id: number
  score_run_status: string
  callsign: string
  category_values: Record<string, string>
  result_status: string
  included_by_default: boolean
  score: number
  explanation: Record<string, unknown>
}

export interface ResultReview {
  contest_id: number
  contest_slug: string
  status: string
  publication_policy: Record<string, boolean>
  items: ManagerResultCandidate[]
  unresolved: Array<Record<string, unknown>>
  unresolved_count: number
}

export interface GeneratedResults {
  contest_id: number
  score_runs: Array<{ id: number; entry_id: number; status: string }>
  unresolved_count: number
  unresolved: Array<Record<string, unknown>>
}

export interface PublishedResult {
  id: number
  contest_id: number
  publication_number: number
  source_digest: string
  entry_count: number
  withheld_count: number
  published_at: string
  status: string
}

export function listPublicContests(signal?: AbortSignal) {
  return apiRequest<PublicContestList>(
    '/public/contests?page=1&page_size=50&sort=starts_at&order=desc',
    { signal },
  )
}

export function listUpcomingContests(signal?: AbortSignal) {
  return apiRequest<UpcomingContestList>(
    '/public/contests/upcoming?page=1&page_size=50',
    { signal },
  )
}

export function getPublicContest(slug: string, signal?: AbortSignal) {
  return apiRequest<PublicContestDetails>(
    `/public/contests/${encodeURIComponent(slug)}`,
    { signal },
  )
}

export function getPublicResults(
  slug: string,
  filters: {
    page?: number
    category?: string
    value?: string
    band?: string
    mode?: string
    status?: string
  } = {},
  signal?: AbortSignal,
) {
  const query = new URLSearchParams({
    page: String(filters.page ?? 1),
    page_size: '50',
    sort: 'placement',
    order: 'asc',
  })
  for (const key of ['category', 'value', 'band', 'mode', 'status'] as const) {
    const value = filters[key]
    if (value) query.set(key, value)
  }
  return apiRequest<PublicResultsPage>(
    `/public/contests/${encodeURIComponent(slug)}/results?${query.toString()}`,
    { signal },
  )
}

export function getManagerResultReview(
  contestId: number,
  signal?: AbortSignal,
) {
  return apiRequest<ResultReview>(`/contests/${contestId}/results/review`, {
    signal,
  })
}

export function generateResults(contestId: number, reason?: string) {
  return apiRequest<GeneratedResults>(
    `/contests/${contestId}/results/generate`,
    {
      method: 'POST',
      headers: { 'Idempotency-Key': crypto.randomUUID() },
      body: JSON.stringify({ reason: reason || null }),
    },
  )
}

export function publishResults(
  contestId: number,
  scoreRunIds: number[],
  reason?: string,
) {
  return apiRequest<PublishedResult>(`/contests/${contestId}/results/publish`, {
    method: 'POST',
    body: JSON.stringify({
      score_run_ids: scoreRunIds,
      reason: reason || null,
    }),
  })
}

export function recordQsoReview(
  contestId: number,
  qsoId: number,
  review: {
    status: 'credited' | 'not_credited' | 'needs_review'
    reason: string
  },
) {
  return apiRequest<{ status: string }>(
    `/contests/${contestId}/qsos/${qsoId}/decisions`,
    {
      method: 'POST',
      body: JSON.stringify({
        status: review.status,
        reason_code: 'manager_review',
        reason: review.reason,
        evidence: {},
      }),
    },
  )
}

export function updateEntryStatus(
  contestId: number,
  entryId: number,
  status: 'accepted' | 'checklog' | 'withdrawn' | 'disqualified',
) {
  return apiRequest<{ entry_id: number; status: string }>(
    `/contests/${contestId}/entries/${entryId}/status`,
    {
      method: 'PUT',
      body: JSON.stringify({ status, audit_reason: 'Phase 8 result review' }),
    },
  )
}
