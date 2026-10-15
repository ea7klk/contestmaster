import { apiRequest } from './client'

export interface PrivilegedUser {
  id: number
  username: string
  email: string
  display_name: string
  role: 'global_administrator' | 'contest_manager'
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
