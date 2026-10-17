import { ApiError } from './client'
import { apiRequest } from './client'

export interface SubmitContest {
  id: number
  name: string
  slug: string
  cutoff_at: string
  accepted_formats: Array<'cabrillo' | 'adif'>
}

export interface ImportMessage {
  line: number
  code: string
  message: string
}

export interface LogSubmissionResult {
  status: 'accepted' | 'rejected'
  replayed?: boolean
  entry_id?: number
  entry_key?: string
  revision_number?: number
  receipt_token?: string | null
  guest_email_prompt_required?: boolean
  guest_email_verification_sent?: boolean | null
  guest_email_verification_queued?: boolean | null
  summary: {
    accepted_qsos: number
    rejected_qsos: number
    error_count: number
    warning_count: number
  }
  errors: ImportMessage[]
  warnings: ImportMessage[]
}

export interface EntryContact {
  id: number
  occurred_at: string
  callsign: string
  frequency: string | null
  mode: string | null
  exchange_sent: Record<string, string>
  exchange_received: Record<string, string>
}

export interface ManagedEntry {
  entry_id: number
  contest_id: number
  accepted_formats: Array<'cabrillo' | 'adif'>
  entry_key: string
  category_values: Record<string, string>
  revision_number: number | null
  revision_id: number | null
  contacts: EntryContact[]
}

export interface ContestLogSummary {
  entry_id: number
  entry_key: string
  callsign: string
  status: string
  is_late: boolean
  category_values: Record<string, string>
  submitted_at: string
  revision_id: number | null
  revision_number: number | null
  input_format: string | null
  original_filename: string | null
  qso_count: number
}

export interface ContestLogList {
  items: ContestLogSummary[]
  meta: { page: number; page_size: number; total: number; pages: number }
}

export interface ContestLogRevision {
  id: number
  revision_number: number
  input_format: string
  original_filename: string | null
  byte_size: number
  submitted_at: string
  received_at: string
  qso_count: number
}

export interface ContestLogDetails {
  entry: ContestLogSummary & { revision_count: number }
  revisions: ContestLogRevision[]
  contacts: Array<{
    id: number
    source_line_number: number | null
    occurred_at: string
    callsign: string
    band: string | null
    mode: string | null
    exchange_sent: Record<string, unknown>
    exchange_received: Record<string, unknown>
  }>
  meta: { page: number; page_size: number; total: number; pages: number }
}

export function listContestLogs(
  contestId: number,
  page: number,
  search: string,
  signal?: AbortSignal,
) {
  const params = new URLSearchParams({ page: String(page), page_size: '50' })
  if (search.trim()) params.set('search', search.trim())
  return apiRequest<ContestLogList>(
    `/contests/${contestId}/entries?${params.toString()}`,
    { method: 'GET', signal },
  )
}

export function getContestLogDetails(
  contestId: number,
  entryId: number,
  page: number,
  revisionId?: number,
  signal?: AbortSignal,
) {
  const params = new URLSearchParams({ page: String(page), page_size: '50' })
  if (revisionId) params.set('revision_id', String(revisionId))
  return apiRequest<ContestLogDetails>(
    `/contests/${contestId}/entries/${entryId}?${params.toString()}`,
    { method: 'GET', signal },
  )
}

export async function downloadContestLogRevision(
  contestId: number,
  entryId: number,
  revisionId: number,
): Promise<{ blob: Blob; filename: string }> {
  const response = await fetch(
    `${apiPrefix}/contests/${contestId}/entries/${entryId}/revisions/${revisionId}/download`,
    { credentials: 'same-origin' },
  )
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as
      | { error?: { message?: string } }
      | null
    throw new ApiError(
      payload?.error?.message ?? `The log download failed with HTTP ${response.status}.`,
      [],
      response.status,
    )
  }
  const disposition = response.headers.get('Content-Disposition') ?? ''
  const filename =
    disposition.match(/filename="([A-Za-z0-9._-]+)"/)?.[1] ??
    `entry-${entryId}-revision-${revisionId}.log`
  return { blob: await response.blob(), filename }
}

export async function downloadEntryRevision(
  entryId: number,
  revisionId: number,
  receiptToken?: string,
): Promise<{ blob: Blob; filename: string }> {
  const headers = new Headers()
  if (receiptToken) headers.set('X-Entry-Receipt', receiptToken)
  let response: Response
  try {
    response = await fetch(
      `${apiPrefix}/public/entries/${entryId}/revisions/${revisionId}/download`,
      { headers, credentials: 'same-origin' },
    )
  } catch {
    throw new ApiError('The log download connection could not be reached.')
  }
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as
      | { error?: { message?: string } }
      | null
    throw new ApiError(
      payload?.error?.message ?? `The log download failed with HTTP ${response.status}.`,
      [],
      response.status,
    )
  }
  const disposition = response.headers.get('Content-Disposition') ?? ''
  const filename = disposition.match(/filename="([A-Za-z0-9._-]+)"/)?.[1] ?? `entry-${entryId}.log`
  return { blob: await response.blob(), filename }
}

export interface ContactWrite {
  occurred_at: string
  callsign: string
  frequency: string
  mode: string
  exchange_sent: Record<string, string>
  exchange_received: Record<string, string>
}

const apiPrefix = import.meta.env.VITE_API_PREFIX ?? '/api/v1'

function requestIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

export async function listSubmittableContests(): Promise<SubmitContest[]> {
  const response = await fetch(`${apiPrefix}/public/submittable-contests`, {
    credentials: 'same-origin',
  })
  const payload = (await response.json()) as {
    items?: SubmitContest[]
    error?: { message?: string }
  }
  if (!response.ok) {
    throw new ApiError(
      payload.error?.message ?? 'Contest list could not be loaded.',
      [],
      response.status,
    )
  }
  return payload.items ?? []
}

export function newIdempotencyKey(): string {
  return requestIdempotencyKey()
}

export function uploadContestLog(
  contestSlug: string,
  file: File,
  idempotencyKey: string,
  onProgress: (percent: number) => void,
): Promise<LogSubmissionResult> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest()
    request.open(
      'POST',
      `${apiPrefix}/public/contests/${encodeURIComponent(contestSlug)}/logs`,
    )
    request.withCredentials = true
    request.setRequestHeader('Idempotency-Key', idempotencyKey)
    request.upload.onprogress = (event) => {
      if (event.lengthComputable)
        onProgress(Math.round((event.loaded / event.total) * 100))
    }
    request.onerror = () =>
      reject(
        new ApiError(
          'The upload connection was interrupted. Retry this upload.',
        ),
      )
    request.onload = () => {
      let payload: LogSubmissionResult & { error?: { message?: string } }
      try {
        payload = JSON.parse(request.responseText) as LogSubmissionResult & {
          error?: { message?: string }
        }
      } catch {
        reject(
          new ApiError(
            'The server returned an unreadable upload response.',
            [],
            request.status,
          ),
        )
        return
      }
      if (request.status === 422 && payload.status === 'rejected') {
        resolve(payload)
        return
      }
      if (request.status < 200 || request.status >= 300) {
        reject(
          new ApiError(
            payload.error?.message ??
              `Upload failed with HTTP ${request.status}.`,
            [],
            request.status,
          ),
        )
        return
      }
      resolve(payload)
    }
    const form = new FormData()
    form.append('file', file, file.name)
    request.send(form)
  })
}

function receiptHeaders(receiptToken?: string): HeadersInit {
  return receiptToken ? { 'X-Entry-Receipt': receiptToken } : {}
}

export interface GuestEmailPreferences {
  email: string
  entry_access: boolean
  result_notifications: boolean
}

export function setGuestEntryEmail(
  entryId: number,
  preferences: GuestEmailPreferences,
  receiptToken?: string,
) {
  return apiRequest<{
    status: 'revoked' | 'verification_required'
    verified: boolean
    verification_email_sent: boolean | null
    verification_email_queued: boolean | null
  }>(`/public/entries/${entryId}/guest-email`, {
    method: 'POST',
    headers: receiptHeaders(receiptToken),
    body: JSON.stringify(preferences),
  })
}

export function verifyGuestEntryEmail(token: string) {
  return apiRequest<{
    status: 'verified'
    entry_id: number
    entry_access_token: string | null
    results_notifications_enabled: boolean
  }>('/public/guest-email/verify', {
    method: 'POST',
    body: JSON.stringify({ token }),
  })
}

export function resendGuestEntryEmailVerification(
  entryId: number,
  receiptToken?: string,
) {
  return apiRequest<{
    status: string
    verification_email_sent: boolean | null
    verification_email_queued: boolean
  }>(
    `/public/entries/${entryId}/guest-email/resend`,
    { method: 'POST', headers: receiptHeaders(receiptToken) },
  )
}

export function getManagedEntry(entryId: number, receiptToken?: string) {
  return apiRequest<ManagedEntry>(`/public/entries/${entryId}`, {
    headers: receiptHeaders(receiptToken),
  })
}

export function addEntryContact(
  entryId: number,
  contact: ContactWrite,
  receiptToken?: string,
) {
  return apiRequest<ManagedEntry>(`/public/entries/${entryId}/contacts`, {
    method: 'POST',
    headers: receiptHeaders(receiptToken),
    body: JSON.stringify(contact),
  })
}

export function editEntryContact(
  entryId: number,
  contactId: number,
  contact: ContactWrite,
  receiptToken?: string,
) {
  return apiRequest<ManagedEntry>(
    `/public/entries/${entryId}/contacts/${contactId}`,
    {
      method: 'PUT',
      headers: receiptHeaders(receiptToken),
      body: JSON.stringify(contact),
    },
  )
}

export function removeEntryContact(
  entryId: number,
  contactId: number,
  receiptToken?: string,
) {
  return apiRequest<ManagedEntry>(
    `/public/entries/${entryId}/contacts/${contactId}`,
    { method: 'DELETE', headers: receiptHeaders(receiptToken) },
  )
}

export function resubmitEntryLog(
  entryId: number,
  file: File,
  idempotencyKey: string,
  receiptToken: string | undefined,
  onProgress: (percent: number) => void,
): Promise<LogSubmissionResult> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest()
    request.open('PUT', `${apiPrefix}/public/entries/${entryId}/log`)
    request.withCredentials = true
    request.setRequestHeader('Idempotency-Key', idempotencyKey)
    if (receiptToken) request.setRequestHeader('X-Entry-Receipt', receiptToken)
    const csrf = document.cookie.match(
      /(?:^|;\s*)contestmaster_participant_csrf=([^;]+)/,
    )
    if (csrf?.[1])
      request.setRequestHeader('X-CSRF-Token', decodeURIComponent(csrf[1]))
    request.upload.onprogress = (event) => {
      if (event.lengthComputable)
        onProgress(Math.round((event.loaded / event.total) * 100))
    }
    request.onerror = () =>
      reject(
        new ApiError(
          'The upload connection was interrupted. Retry this upload.',
        ),
      )
    request.onload = () => {
      let payload: LogSubmissionResult & { error?: { message?: string } }
      try {
        payload = JSON.parse(request.responseText) as LogSubmissionResult & {
          error?: { message?: string }
        }
      } catch {
        reject(
          new ApiError(
            'The server returned an unreadable upload response.',
            [],
            request.status,
          ),
        )
        return
      }
      if (request.status === 422 && payload.status === 'rejected') {
        resolve(payload)
      } else if (request.status < 200 || request.status >= 300) {
        reject(
          new ApiError(
            payload.error?.message ??
              `Upload failed with HTTP ${request.status}.`,
            [],
            request.status,
          ),
        )
      } else {
        resolve(payload)
      }
    }
    const form = new FormData()
    form.append('file', file, file.name)
    request.send(form)
  })
}
