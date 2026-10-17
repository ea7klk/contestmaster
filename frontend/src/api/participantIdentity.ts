import { apiRequest } from './client'

export interface ParticipantProfile {
  id: number
  email: string
  display_name: string | null
  callsign: string | null
  callsigns?: Array<{ id: number; callsign: string; is_primary: boolean }>
}

export interface ParticipantEntry {
  id: number
  contest_id: number
  contest_name: string
  contest_slug: string
  entry_key: string
  status: string
  submitted_at: string
}

export async function requestParticipantMagicLink(email: string) {
  return apiRequest<{ status: string; message: string }>(
    '/participants/auth/request-link',
    { method: 'POST', body: JSON.stringify({ email }) },
  )
}

export async function registerParticipant(input: {
  email: string
  callsign: string
  password: string
  display_name?: string
}) {
  return apiRequest<{ status: string }>('/participants/auth/register', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export async function loginParticipant(email: string, password: string) {
  return apiRequest<{ participant: ParticipantProfile; csrf_token: string }>(
    '/participants/auth/login',
    { method: 'POST', body: JSON.stringify({ email, password }) },
  )
}

export async function requestParticipantPasswordReset(email: string) {
  return apiRequest<{ status: string; message: string }>(
    '/participants/auth/forgot-password',
    { method: 'POST', body: JSON.stringify({ email }) },
  )
}

export async function resetParticipantPassword(token: string, password: string) {
  return apiRequest<{ status: string }>('/participants/auth/reset-password', {
    method: 'POST',
    body: JSON.stringify({ token, password }),
  })
}

export async function getParticipantProfile() {
  return apiRequest<ParticipantProfile & { callsigns: Array<{ id: number; callsign: string; is_primary: boolean }> }>(
    '/participants/auth/me',
  )
}

export async function addParticipantCallsign(callsign: string) {
  return apiRequest<{ id: number; callsign: string; is_primary: boolean }>(
    '/participants/auth/callsigns',
    { method: 'POST', body: JSON.stringify({ callsign }) },
  )
}

export async function removeParticipantCallsign(callsignId: number) {
  return apiRequest<void>(`/participants/auth/callsigns/${callsignId}`, { method: 'DELETE' })
}

export async function updateParticipantProfile(display_name: string | null) {
  return apiRequest<{ id: number; display_name: string | null }>('/participants/auth/me', {
    method: 'PATCH', body: JSON.stringify({ display_name }),
  })
}

export async function withdrawParticipantEntry(entryId: number) {
  return apiRequest<{ status: string }>(`/public/entries/${entryId}/withdraw`, {
    method: 'POST',
  })
}

export async function requestParticipantEmailChange(email: string) {
  return apiRequest<{ status: string }>('/participants/auth/email-change', {
    method: 'POST',
    body: JSON.stringify({ email }),
  })
}

export async function confirmParticipantEmailChange(token: string) {
  return apiRequest<{ status: string; complete: string }>(
    '/participants/auth/confirm-email-change',
    { method: 'POST', body: JSON.stringify({ token }) },
  )
}

export async function consumeParticipantMagicLink(token: string) {
  return apiRequest<{ participant: ParticipantProfile; csrf_token: string }>(
    '/participants/auth/consume-link',
    { method: 'POST', body: JSON.stringify({ token }) },
  )
}

export async function getParticipantEntries() {
  return apiRequest<{ items: ParticipantEntry[] }>('/participants/auth/entries')
}

export async function claimParticipantEntries(receiptToken: string) {
  return apiRequest<{
    status: 'claimed'
    callsign: string
    claimed_entries: number
  }>('/participants/auth/claim-entries', {
    method: 'POST',
    body: JSON.stringify({ receipt_token: receiptToken }),
  })
}

export async function signOutParticipant() {
  return apiRequest<{ status: string }>('/participants/auth/logout', {
    method: 'POST',
  })
}
