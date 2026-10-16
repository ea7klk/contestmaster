import { apiRequest } from './client'

interface CatalogItemBase {
  id: number
  key: string
  label: string
  description: string
  sort_order: number
  is_active: boolean
}

export interface BandCatalogItem extends CatalogItemBase {
  kind: 'band'
  frequency_range: string | null
  contest_free: boolean
}

export interface ModeCatalogItem extends CatalogItemBase {
  kind: 'mode'
}

export type OperatingCatalogItem = BandCatalogItem | ModeCatalogItem
export type BandCatalogInput = Omit<BandCatalogItem, 'id' | 'kind'>
export type ModeCatalogInput = Omit<ModeCatalogItem, 'id' | 'kind'>
export type OperatingCatalogInput = Omit<
  OperatingCatalogItem,
  'id' | 'kind'
> & {
  kind: OperatingCatalogItem['kind']
  frequency_range?: string | null
  contest_free?: boolean
}

export function getBands(signal?: AbortSignal) {
  return apiRequest<{ items: BandCatalogItem[] }>('/rulesets/bands', { signal })
}

export function getModes(signal?: AbortSignal) {
  return apiRequest<{ items: ModeCatalogItem[] }>('/rulesets/modes', { signal })
}

export function getAdminBands(signal?: AbortSignal) {
  return apiRequest<{ items: BandCatalogItem[] }>('/rulesets/admin/bands', {
    signal,
  })
}

export function getAdminModes(signal?: AbortSignal) {
  return apiRequest<{ items: ModeCatalogItem[] }>('/rulesets/admin/modes', {
    signal,
  })
}

export function createBand(input: BandCatalogInput) {
  return apiRequest<BandCatalogItem>('/rulesets/admin/bands', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function updateBand(id: number, input: BandCatalogInput) {
  return apiRequest<BandCatalogItem>(`/rulesets/admin/bands/${id}`, {
    method: 'PUT',
    body: JSON.stringify(input),
  })
}

export function deleteBand(id: number) {
  return apiRequest<void>(`/rulesets/admin/bands/${id}`, { method: 'DELETE' })
}

export function createMode(input: ModeCatalogInput) {
  return apiRequest<ModeCatalogItem>('/rulesets/admin/modes', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function updateMode(id: number, input: ModeCatalogInput) {
  return apiRequest<ModeCatalogItem>(`/rulesets/admin/modes/${id}`, {
    method: 'PUT',
    body: JSON.stringify(input),
  })
}

export function deleteMode(id: number) {
  return apiRequest<void>(`/rulesets/admin/modes/${id}`, { method: 'DELETE' })
}

/** Legacy combined read retained for integrations still migrating to split resources. */
export function getOperatingCatalog(signal?: AbortSignal) {
  return apiRequest<{ items: OperatingCatalogItem[] }>(
    '/rulesets/operating-catalog',
    { signal },
  )
}

/** Legacy combined read retained for integrations still migrating to split resources. */
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
