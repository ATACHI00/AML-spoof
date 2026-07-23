'use client'

import { useEffect, useState } from 'react'
import {
  ComplianceStats,
  AuditLogEntry,
  AuditVerifyResponse,
  getComplianceStats,
  listAuditLogs,
  verifyAuditChain,
  getExportAlertsUrl,
  formatDate,
  SEVERITY_COLORS,
  STATUS_COLORS,
} from '../api'

export default function CompliancePage() {
  const [stats, setStats] = useState<ComplianceStats | null>(null)
  const [auditLogs, setAuditLogs] = useState<AuditLogEntry[]>([])
  const [auditVerify, setAuditVerify] = useState<AuditVerifyResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [auditPage, setAuditPage] = useState(1)
  const [auditTotal, setAuditTotal] = useState(0)
  const [verifyLoading, setVerifyLoading] = useState(false)

  useEffect(() => {
    loadData()
  }, [auditPage])

  async function loadData() {
    setLoading(true)
    setError(null)
    try {
      const [statsData, auditData] = await Promise.all([
        getComplianceStats(),
        listAuditLogs({ page: auditPage, page_size: 20 }),
      ])
      setStats(statsData)
      setAuditLogs(auditData.items)
      setAuditTotal(auditData.total)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load compliance data')
    } finally {
      setLoading(false)
    }
  }

  async function handleVerify() {
    setVerifyLoading(true)
    try {
      const result = await verifyAuditChain()
      setAuditVerify(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Verification failed')
    } finally {
      setVerifyLoading(false)
    }
  }

  const totalPages = Math.ceil(auditTotal / 20)

  return (
    <div style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
      <h1 style={{ fontSize: '24px', fontWeight: 700, marginBottom: '24px' }}>
        Compliance Dashboard
      </h1>

      {error && (
        <div style={{
          padding: '12px 16px',
          background: '#fef2f2',
          color: '#dc2626',
          borderRadius: '8px',
          marginBottom: '16px',
          border: '1px solid #fecaca',
        }}>
          {error}
        </div>
      )}

      {loading && !stats && (
        <div style={{ textAlign: 'center', padding: '48px', color: '#6b7280' }}>
          Loading compliance data...
        </div>
      )}

      {stats && (
        <>
          {/* Stats Cards */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: '16px',
            marginBottom: '32px',
          }}>
            <StatCard title="Total Alerts" value={stats.total_alerts} color="#3b82f6" />
            <StatCard title="Open Cases" value={stats.open_cases} color="#f59e0b" />
            <StatCard title="Total Cases" value={stats.total_cases} color="#6b7280" />
            <StatCard title="Transactions" value={stats.total_transactions} color="#10b981" />
            <StatCard title="Audit Entries" value={stats.total_audit_entries} color="#8b5cf6" />
          </div>

          {/* Severity & Status Breakdown */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
            gap: '24px',
            marginBottom: '32px',
          }}>
            <div style={{
              background: 'var(--gray-900)',
              borderRadius: '8px',
              padding: '20px',
              border: '1px solid #e5e7eb',
            }}>
              <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '12px' }}>
                Alerts by Severity
              </h3>
              {Object.entries(stats.alerts_by_severity).length === 0 ? (
                <p style={{ color: '#9ca3af', fontSize: '14px' }}>No alerts</p>
              ) : (
                Object.entries(stats.alerts_by_severity).map(([severity, count]) => (
                  <Bar key={severity} label={severity} value={count} color={SEVERITY_COLORS[severity] || '#6b7280'} />
                ))
              )}
            </div>

            <div style={{
              background: 'var(--gray-900)',
              borderRadius: '8px',
              padding: '20px',
              border: '1px solid #e5e7eb',
            }}>
              <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '12px' }}>
                Alerts by Status
              </h3>
              {Object.entries(stats.alerts_by_status).length === 0 ? (
                <p style={{ color: '#9ca3af', fontSize: '14px' }}>No alerts</p>
              ) : (
                Object.entries(stats.alerts_by_status).map(([status, count]) => (
                  <Bar key={status} label={status} value={count} color={STATUS_COLORS[status] || '#6b7280'} />
                ))
              )}
            </div>
          </div>

          {/* Export Actions */}
          <div style={{
            display: 'flex',
            gap: '12px',
            marginBottom: '32px',
            flexWrap: 'wrap',
          }}>
            <a
              href={getExportAlertsUrl()}
              style={buttonStyle('#10b981')}
            >
              ⬇ Export All Alerts (CSV)
            </a>
            <a
              href={getExportAlertsUrl('new')}
              style={buttonStyle('#3b82f6')}
            >
              ⬇ Export New Alerts (CSV)
            </a>
            <a
              href={getExportAlertsUrl(undefined, 'critical')}
              style={buttonStyle('#7c3aed')}
            >
              ⬇ Export Critical Alerts (CSV)
            </a>
          </div>

          {/* Audit Log Verification */}
          <div style={{
            background: 'var(--gray-900)',
            borderRadius: '8px',
            padding: '20px',
            border: '1px solid #e5e7eb',
            marginBottom: '32px',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
              <h3 style={{ fontSize: '16px', fontWeight: 600 }}>
                Audit Log Integrity
              </h3>
              <button
                onClick={handleVerify}
                disabled={verifyLoading}
                style={{
                  padding: '8px 16px',
                  background: verifyLoading ? '#d1d5db' : '#8b5cf6',
                  color: 'white',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: verifyLoading ? 'not-allowed' : 'pointer',
                  fontSize: '14px',
                }}
              >
                {verifyLoading ? 'Verifying...' : 'Verify Hash Chain'}
              </button>
            </div>

            {auditVerify && (
              <div style={{
                padding: '12px',
                borderRadius: '6px',
                background: auditVerify.is_intact ? '#F37021' : '#fef2f2',
                border: `1px solid ${auditVerify.is_intact ? '#bbf7d0' : '#fecaca'}`,
                color: auditVerify.is_intact ? '#1a1a1a' : '#dc2626',
                fontSize: '14px',
              }}>
                {auditVerify.is_intact ? (
                  <>✅ Hash chain intact — {auditVerify.total_entries} entries verified</>
                ) : (
                  <>⚠️ Hash chain compromised — {auditVerify.broken_links.length} broken link(s) found</>
                )}
              </div>
            )}
          </div>

          {/* Audit Log Viewer */}
          <div style={{
            background: 'var(--gray-900)',
            borderRadius: '8px',
            padding: '20px',
            border: '1px solid #e5e7eb',
          }}>
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '16px' }}>
              Recent Audit Log Entries
            </h3>

            {auditLogs.length === 0 ? (
              <p style={{ color: '#9ca3af', fontSize: '14px' }}>No audit log entries</p>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
                  <thead>
                    <tr style={{ borderBottom: '2px solid #e5e7eb' }}>
                      <th style={thStyle}>Time</th>
                      <th style={thStyle}>Entity</th>
                      <th style={thStyle}>Action</th>
                      <th style={thStyle}>Actor</th>
                      <th style={thStyle}>Hash</th>
                    </tr>
                  </thead>
                  <tbody>
                    {auditLogs.map((log) => (
                      <tr key={log.id} style={{ borderBottom: '1px solid #e5e7eb' }}>
                        <td style={tdStyle}>{formatDate(log.created_at)}</td>
                        <td style={tdStyle}>
                          <span style={{ fontSize: '12px', color: '#6b7280' }}>{log.entity_type}</span>
                          <br />
                          <span style={{ fontSize: '11px', fontFamily: 'monospace' }}>
                            {log.entity_id.substring(0, 8)}...
                          </span>
                        </td>
                        <td style={tdStyle}>
                          <span style={{
                            padding: '2px 6px',
                            borderRadius: '4px',
                            fontSize: '12px',
                            background: log.action.includes('status_') ? '#dbeafe' : '#f3f4f6',
                            color: log.action.includes('status_') ? '#1d4ed8' : '#374151',
                          }}>
                            {log.action}
                          </span>
                        </td>
                        <td style={tdStyle}>{log.actor_id}</td>
                        <td style={{ ...tdStyle, fontFamily: 'monospace', fontSize: '11px' }}>
                          {log.current_hash.substring(0, 12)}...
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Pagination */}
            {totalPages > 1 && (
              <div style={{ display: 'flex', justifyContent: 'center', gap: '8px', marginTop: '16px' }}>
                <button
                  onClick={() => setAuditPage(p => Math.max(1, p - 1))}
                  disabled={auditPage === 1}
                  style={pageButtonStyle(auditPage === 1)}
                >
                  Previous
                </button>
                <span style={{ padding: '8px 12px', fontSize: '14px', color: '#6b7280' }}>
                  Page {auditPage} of {totalPages}
                </span>
                <button
                  onClick={() => setAuditPage(p => Math.min(totalPages, p + 1))}
                  disabled={auditPage === totalPages}
                  style={pageButtonStyle(auditPage === totalPages)}
                >
                  Next
                </button>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

function StatCard({ title, value, color }: { title: string; value: number; color: string }) {
  return (
    <div style={{
      background: 'white',
      borderRadius: '8px',
      padding: '20px',
      border: '1px solid #e5e7eb',
      borderLeft: `4px solid ${color}`,
    }}>
      <div style={{ fontSize: '14px', color: '#6b7280', marginBottom: '4px' }}>{title}</div>
      <div style={{ fontSize: '28px', fontWeight: 700, color }}>{value.toLocaleString()}</div>
    </div>
  )
}

function Bar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div style={{ marginBottom: '8px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px', marginBottom: '4px' }}>
        <span style={{ textTransform: 'capitalize' }}>{label}</span>
        <span style={{ fontWeight: 600 }}>{value}</span>
      </div>
      <div style={{
        height: '8px',
        background: '#f3f4f6',
        borderRadius: '4px',
        overflow: 'hidden',
      }}>
        <div style={{
          height: '100%',
          width: `${Math.min(100, value * 10)}%`,
          background: color,
          borderRadius: '4px',
          transition: 'width 0.3s ease',
        }} />
      </div>
    </div>
  )
}

const thStyle: React.CSSProperties = {
  textAlign: 'left',
  padding: '8px 12px',
  fontWeight: 600,
  color: '#374151',
  whiteSpace: 'nowrap',
}

const tdStyle: React.CSSProperties = {
  padding: '8px 12px',
  color: '#4b5563',
}

function buttonStyle(color: string): React.CSSProperties {
  return {
    display: 'inline-block',
    padding: '10px 20px',
    background: color,
    color: 'white',
    borderRadius: '6px',
    textDecoration: 'none',
    fontSize: '14px',
    fontWeight: 500,
  }
}

function pageButtonStyle(disabled: boolean): React.CSSProperties {
  return {
    padding: '8px 16px',
    background: disabled ? '#f3f4f6' : 'white',
    color: disabled ? '#9ca3af' : '#374151',
    border: '1px solid #d1d5db',
    borderRadius: '6px',
    cursor: disabled ? 'not-allowed' : 'pointer',
    fontSize: '14px',
  }
}