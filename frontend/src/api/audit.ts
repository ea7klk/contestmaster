import { apiRequest } from './client'

export interface AuditEventRecord {
  id: number
  occurred_at: string
  actor_user_id: number | null
  actor: string | null
  action: string
  target_type: string
  target_id: string
  reason: string | null
  metadata: Record<string, unknown>
  request_id: string | null
}

export interface AuditEventFilters {
  q?: string
  action?: string
  target_type?: string
  from_at?: string
  to_at?: string
  page?: number
  page_size?: number
}

export async function searchAuditEvents(filters: AuditEventFilters = {}) {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== '') params.set(key, String(value))
  }
  const query = params.size ? `?${params.toString()}` : ''
  return apiRequest<{
    items: AuditEventRecord[]
    total: number
    page: number
    page_size: number
    retention_days: number
  }>(`/admin/audit-events${query}`)
}
