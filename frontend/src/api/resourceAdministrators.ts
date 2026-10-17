import { apiRequest } from './client'

export interface ResourceAdministrator {
  user_id: number
  username: string
  display_name: string
}

export interface ResourceAdministratorList {
  owner_user_id: number
  items: ResourceAdministrator[]
  eligible: ResourceAdministrator[]
}

export async function getResourceAdministrators(kind: 'contest' | 'ruleset', id: number) {
  const path = kind === 'contest' ? `/contests/${id}/administrators` : `/rulesets/${id}/administrators`
  return apiRequest<ResourceAdministratorList>(path)
}

export async function addResourceAdministrator(kind: 'contest' | 'ruleset', id: number, user_id: number) {
  const path = kind === 'contest' ? `/contests/${id}/administrators` : `/rulesets/${id}/administrators`
  return apiRequest<ResourceAdministrator>(path, { method: 'POST', body: JSON.stringify({ user_id }) })
}

export async function removeResourceAdministrator(kind: 'contest' | 'ruleset', id: number, userId: number) {
  const path = kind === 'contest' ? `/contests/${id}/administrators/${userId}` : `/rulesets/${id}/administrators/${userId}`
  return apiRequest<void>(path, { method: 'DELETE' })
}
