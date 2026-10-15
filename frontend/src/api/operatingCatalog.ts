import { apiRequest } from './client'

export interface OperatingCatalogItem {
  id: number
  kind: 'band' | 'mode'
  key: string
  label: string
  description: string
  frequency_range: string | null
  sort_order: number
  is_active: boolean
  contest_free: boolean
}

export type OperatingCatalogInput = Omit<OperatingCatalogItem, 'id'>

export function getOperatingCatalog(signal?: AbortSignal) {
  return apiRequest<{ items: OperatingCatalogItem[] }>(
    '/rulesets/operating-catalog',
    { signal },
  )
}

export function getAdminOperatingCatalog(signal?: AbortSignal) {
  return apiRequest<{ items: OperatingCatalogItem[] }>(
    '/rulesets/admin/operating-catalog',
    { signal },
  )
}

export function createOperatingCatalogItem(input: OperatingCatalogInput) {
  return apiRequest<OperatingCatalogItem>('/rulesets/admin/operating-catalog', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function updateOperatingCatalogItem(
  id: number,
  input: OperatingCatalogInput,
) {
  return apiRequest<OperatingCatalogItem>(
    `/rulesets/admin/operating-catalog/${id}`,
    { method: 'PUT', body: JSON.stringify(input) },
  )
}

export function deleteOperatingCatalogItem(id: number) {
  return apiRequest<void>(`/rulesets/admin/operating-catalog/${id}`, {
    method: 'DELETE',
  })
}
