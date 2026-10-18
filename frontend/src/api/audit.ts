import { apiRequest } from './client'

export interface AuditEventRecord {
  id: number
  occurred_at: string
  actor_user_id: number | null
  actor: string | null
  action: string
  target_type: string
  target_id: string
  target_name: string
  reason: string | null
  metadata: Record<string, unknown>
  request_id: string | null
}

export interface AuditEventFilters {
  q?: string
  action?: string[]
  target_type?: string[]
  from_at?: string
  to_at?: string
  page?: number
  page_size?: number
}

export async function searchAuditEvents(filters: AuditEventFilters = {}) {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (value === undefined || value === '') continue
    if (Array.isArray(value)) {
      for (const item of value) params.append(key, item)
    } else {
      params.set(key, String(value))
    }
  }
  const query = params.size ? `?${params.toString()}` : ''
  return apiRequest<{
    items: AuditEventRecord[]
    total: number
    page: number
    page_size: number
    retention_days: number
    action_options: string[]
    target_type_options: string[]
  }>(`/admin/audit-events${query}`)
}
