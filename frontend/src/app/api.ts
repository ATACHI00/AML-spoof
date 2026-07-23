/**
 * AML Monitor — API client
 *
 * Centralized API client for communicating with the backend.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || 'dev-api-key-1'

export interface Alert {
  id: string
  transaction_id: string | null
  rule_id: string | null
  case_id: string | null
  severity: 'low' | 'medium' | 'high' | 'critical'
  risk_score: string | null
  title: string
  description: string | null
  status: 'new' | 'in_review' | 'escalated' | 'closed'
  created_at: string
  updated_at: string
}

export interface AlertListResponse {
  alerts: Alert[]
  total: number
  page: number
  page_size: number
}

export interface AlertStatusUpdateResponse {
  alert: Alert
  audit_entry_id: string
  message: string
}

export interface AlertFilters {
  page?: number
  page_size?: number
  status?: string
  severity?: string
  rule_id?: string
  sort_by?: string
  sort_order?: string
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${API_URL}${path}`
  const res = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': API_KEY,
      ...options?.headers,
    },
  })

  if (!res.ok) {
    const body = await res.text()
    throw new Error(`API error ${res.status}: ${body}`)
  }

  return res.json()
}

export async function listAlerts(filters: AlertFilters = {}): Promise<AlertListResponse> {
  const params = new URLSearchParams()
  if (filters.page) params.set('page', String(filters.page))
  if (filters.page_size) params.set('page_size', String(filters.page_size))
  if (filters.status) params.set('status', filters.status)
  if (filters.severity) params.set('severity', filters.severity)
  if (filters.rule_id) params.set('rule_id', filters.rule_id)
  if (filters.sort_by) params.set('sort_by', filters.sort_by)
  if (filters.sort_order) params.set('sort_order', filters.sort_order)

  const qs = params.toString()
  return request<AlertListResponse>(`/api/v1/alerts/${qs ? `?${qs}` : ''}`)
}

export async function getAlert(id: string): Promise<Alert> {
  return request<Alert>(`/api/v1/alerts/${id}`)
}

export async function updateAlertStatus(
  id: string,
  status: string,
  comment: string,
  actorId: string = 'compliance-officer',
): Promise<AlertStatusUpdateResponse> {
  return request<AlertStatusUpdateResponse>(`/api/v1/alerts/${id}/status`, {
    method: 'PATCH',
    body: JSON.stringify({ status, comment, actor_id: actorId }),
  })
}

export const SEVERITY_COLORS: Record<string, string> = {
  low: '#6b7280',
  medium: '#f59e0b',
  high: '#ef4444',
  critical: '#7c3aed',
}

export const STATUS_COLORS: Record<string, string> = {
  new: '#3b82f6',
  in_review: '#f59e0b',
  escalated: '#ef4444',
  closed: '#6b7280',
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleString('en-GB', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// ---------------------------------------------------------------------------
// Transactions API
// ---------------------------------------------------------------------------

export interface Transaction {
  id: string
  external_id: string
  source_account_id: string | null
  destination_account_id: string | null
  amount: string
  currency: string
  txn_timestamp: string
  channel: string | null
  status: string
  extra_data: any
  created_at: string
  ingested_at: string
}

export interface TransactionListResponse {
  transactions: Transaction[]
  total: number
}

export async function listTransactions(page: number = 1, pageSize: number = 100): Promise<TransactionListResponse> {
  const params = new URLSearchParams()
  params.set('page', String(page))
  params.set('page_size', String(pageSize))

  return request<TransactionListResponse>(`/api/v1/transactions/${params.toString() ? `?${params.toString()}` : ''}`)
}

// ---------------------------------------------------------------------------
// Compliance & Audit API
// ---------------------------------------------------------------------------

export interface ComplianceStats {
  total_alerts: number
  alerts_by_severity: Record<string, number>
  alerts_by_status: Record<string, number>
  total_transactions: number
  total_cases: number
  open_cases: number
  total_audit_entries: number
}

export interface AuditLogEntry {
  id: string
  entity_type: string
  entity_id: string
  action: string
  actor_id: string
  changes: Record<string, unknown> | null
  previous_hash: string | null
  current_hash: string
  created_at: string
}

export interface AuditLogListResponse {
  items: AuditLogEntry[]
  total: number
  page: number
  page_size: number
}

export interface AuditVerifyResponse {
  is_intact: boolean
  total_entries: number
  broken_links: Array<{
    id: string
    expected_hash: string
    actual_hash: string
    created_at: string
  }>
}

export async function getComplianceStats(): Promise<ComplianceStats> {
  return request<ComplianceStats>('/api/v1/compliance/stats')
}

export async function listAuditLogs(params: {
  entity_type?: string
  entity_id?: string
  action?: string
  page?: number
  page_size?: number
} = {}): Promise<AuditLogListResponse> {
  const qs = new URLSearchParams()
  if (params.entity_type) qs.set('entity_type', params.entity_type)
  if (params.entity_id) qs.set('entity_id', params.entity_id)
  if (params.action) qs.set('action', params.action)
  if (params.page) qs.set('page', String(params.page))
  if (params.page_size) qs.set('page_size', String(params.page_size))

  const query = qs.toString()
  return request<AuditLogListResponse>(`/api/v1/audit/logs${query ? `?${query}` : ''}`)
}

export async function verifyAuditChain(): Promise<AuditVerifyResponse> {
  return request<AuditVerifyResponse>('/api/v1/audit/verify')
}

export function getExportAlertsUrl(status?: string, severity?: string): string {
  const params = new URLSearchParams()
  if (status) params.set('status', status)
  if (severity) params.set('severity', severity)
  const qs = params.toString()
  return `${API_URL}/api/v1/compliance/export/alerts.csv${qs ? `?${qs}` : ''}`
}

export function getAlertReportUrl(alertId: string): string {
  return `${API_URL}/api/v1/compliance/export/alert/${alertId}/report`
}