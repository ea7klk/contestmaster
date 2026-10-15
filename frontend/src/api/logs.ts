import { ApiError } from './client'
import { apiRequest } from './client'

export interface SubmitContest {
  id: number
  name: string
  slug: string
  cutoff_at: string
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
  entry_key: string
  category_values: Record<string, string>
  revision_number: number | null
  contacts: EntryContact[]
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
