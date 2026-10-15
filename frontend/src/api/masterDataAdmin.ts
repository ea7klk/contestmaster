import { apiRequest } from './client'

export interface MasterDataSyncRun {
  id: number
  dataset_key: string
  source_key: string
  source_name: string
  started_at: string
  finished_at: string | null
  retrieved_at: string | null
  source_url: string | null
  source_release: string | null
  checksum: string | null
  parser_version: string | null
  status: string
  change_detected: boolean | null
  record_counts: Record<string, number>
  error_summary: string | null
}

export interface MasterDataVersion {
  id: number
  dataset_key: string
  status: 'candidate' | 'active' | 'retired' | 'rejected'
  is_current: boolean
  valid_from: string
  valid_to: string | null
  activated_at: string | null
  created_at: string
  provenance: MasterDataSyncRun
  references: {
    contest: number
    score_run: number
    qso_resolution: number
  }
  can_activate: boolean
  can_delete: boolean
}

export async function listMasterDataVersions() {
  return apiRequest<{ items: MasterDataVersion[] }>(
    '/admin/master-data/versions',
  )
}

export async function listMasterDataSyncRuns() {
  return apiRequest<{ items: MasterDataSyncRun[] }>(
    '/admin/master-data/sync-runs',
  )
}

function reasonSuffix(reason?: string): string {
  return reason ? '?audit_reason=' + encodeURIComponent(reason) : ''
}

export async function activateMasterDataVersion(
  versionId: number,
  reason?: string,
) {
  return apiRequest<{ id: number; dataset_key: string; status: string }>(
    `/admin/master-data/versions/${versionId}/activate${reasonSuffix(reason)}`,
    { method: 'POST' },
  )
}

export async function deleteMasterDataVersion(
  versionId: number,
  reason?: string,
) {
  return apiRequest<void>(
    `/admin/master-data/versions/${versionId}${reasonSuffix(reason)}`,
    {
      method: 'DELETE',
    },
  )
}
