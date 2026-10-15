import { apiRequest } from './client'

export interface ParticipantProfile {
  id: number
  email: string
  display_name: string | null
  callsign: string | null
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

export async function consumeParticipantMagicLink(token: string) {
  return apiRequest<{ participant: ParticipantProfile; csrf_token: string }>(
    '/participants/auth/consume-link',
    { method: 'POST', body: JSON.stringify({ token }) },
  )
}

export async function getParticipantEntries() {
  return apiRequest<{ items: ParticipantEntry[] }>('/participants/auth/entries')
}

export async function signOutParticipant() {
  return apiRequest<{ status: string }>('/participants/auth/logout', {
    method: 'POST',
  })
}
