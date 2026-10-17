import { apiRequest } from './client'

export interface PrivilegedUser {
  id: number
  username: string
  email: string
  display_name: string
  role: 'global_administrator' | 'contest_admin' | 'contest_manager'
  is_active?: boolean
  must_change_password: boolean
}

export async function signIn(email: string, password: string) {
  return apiRequest<{ user: PrivilegedUser; csrf_token: string }>(
    '/auth/login',
    {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    },
  )
}

export async function signOut() {
  return apiRequest<{ status: 'signed_out' }>('/auth/logout', {
    method: 'POST',
  })
}

export async function getCurrentUser(signal?: AbortSignal) {
  return apiRequest<PrivilegedUser>('/auth/me', { method: 'GET', signal })
}

export interface SystemUserRecord extends PrivilegedUser { is_active: boolean }

export async function listSystemUsers(q = '') {
  const query = q ? `?q=${encodeURIComponent(q)}` : ''
  return apiRequest<{ items: SystemUserRecord[]; total: number; page: number; page_size: number }>(`/auth/admin/users${query}`)
}

export async function createSystemUser(input: {
  username: string
  email: string
  display_name: string
  password: string
  role: 'global_administrator' | 'contest_admin'
  must_change_password: boolean
}) {
  return apiRequest<SystemUserRecord>('/auth/admin/users', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export async function updateSystemUser(userId: number, input: Partial<Pick<SystemUserRecord, 'username' | 'email' | 'display_name' | 'role' | 'is_active'>>) {
  return apiRequest<SystemUserRecord>(`/auth/admin/users/${userId}`, {
    method: 'PATCH',
    body: JSON.stringify(input),
  })
}

export async function requestSystemPasswordReset(email: string) {
  return apiRequest<{ status: string; message: string }>('/auth/forgot-password', {
    method: 'POST', body: JSON.stringify({ email }),
  })
}

export async function resetSystemPassword(token: string, password: string) {
  return apiRequest<{ status: string }>('/auth/reset-password', {
    method: 'POST', body: JSON.stringify({ token, password }),
  })
}

export async function changeSystemPassword(currentPassword: string, newPassword: string) {
  return apiRequest<{ status: string; user: PrivilegedUser }>('/auth/change-password', {
    method: 'POST',
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  })
}

export interface ParticipantAccountRecord {
  id: number
  display_name: string | null
  is_active: boolean
  has_password: boolean
  emails: Array<{ email: string; verified: boolean; active: boolean }>
  callsigns: string[]
}

export async function listParticipantAccounts(q = '') {
  const query = q ? `?q=${encodeURIComponent(q)}` : ''
  return apiRequest<{ items: ParticipantAccountRecord[] }>(`/auth/admin/participants${query}`)
}

export async function updateParticipantAccount(
  participantId: number,
  input: Pick<ParticipantAccountRecord, 'display_name' | 'is_active'>,
) {
  return apiRequest<Pick<ParticipantAccountRecord, 'id' | 'display_name' | 'is_active'>>(
    `/auth/admin/participants/${participantId}`,
    { method: 'PATCH', body: JSON.stringify(input) },
  )
}
