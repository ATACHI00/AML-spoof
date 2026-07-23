'use client'

import { useEffect, useState, useCallback } from 'react'
import {
  Alert,
  AlertFilters,
  SEVERITY_COLORS,
  STATUS_COLORS,
  formatDate,
  listAlerts,
} from '../api'

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(20)
  const [filterStatus, setFilterStatus] = useState<string>('')
  const [filterSeverity, setFilterSeverity] = useState<string>('')

  const fetchAlerts = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const filters: AlertFilters = { page, page_size: pageSize }
      if (filterStatus) filters.status = filterStatus
      if (filterSeverity) filters.severity = filterSeverity

      const data = await listAlerts(filters)
      setAlerts(data.alerts)
      setTotal(data.total)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load alerts')
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, filterStatus, filterSeverity])

  useEffect(() => {
    fetchAlerts()
  }, [fetchAlerts])

  const totalPages = Math.ceil(total / pageSize)

  return (
    <div className="container" style={{ paddingTop: '2rem' }}>
      <header style={{ marginBottom: '2rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h1 style={{ fontSize: '1.875rem', fontWeight: 700, color: 'var(--gray-900)' }}>
              Alerts
            </h1>
            <p style={{ color: 'var(--gray-900)', marginTop: '0.25rem' }}>
              {total} alert{total !== 1 ? 's' : ''} found
            </p>
          </div>
          <a
            href="/"
            style={{
              color: 'var(--gray-900)',
              textDecoration: 'none',
              fontSize: '0.875rem',
            }}
          >
            ← Back to Dashboard
          </a>
        </div>
      </header>

      {/* Filters */}
      <div className="card" style={{ marginBottom: '1.5rem', padding: '1rem' }}>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <div>
            <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--gray-500)', display: 'block', marginBottom: '0.25rem' }}>
              Status
            </label>
            <select
              value={filterStatus}
              onChange={(e) => { setFilterStatus(e.target.value); setPage(1) }}
              style={{
                padding: '0.5rem',
                borderRadius: '6px',
                border: '1px solid var(--gray-300)',
                fontSize: '0.875rem',
              }}
            >
              <option value="">All Statuses</option>
              <option value="new">New</option>
              <option value="in_review">In Review</option>
              <option value="escalated">Escalated</option>
              <option value="closed">Closed</option>
            </select>
          </div>

          <div>
            <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--gray-500)', display: 'block', marginBottom: '0.25rem' }}>
              Severity
            </label>
            <select
              value={filterSeverity}
              onChange={(e) => { setFilterSeverity(e.target.value); setPage(1) }}
              style={{
                padding: '0.5rem',
                borderRadius: '6px',
                border: '1px solid var(--gray-300)',
                fontSize: '0.875rem',
              }}
            >
              <option value="">All Severities</option>
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
              <option value="critical">Critical</option>
            </select>
          </div>

          <button
            onClick={fetchAlerts}
            style={{
              padding: '0.5rem 1rem',
              background: 'var(--brand-bg)',
              color: 'white',
              border: 'none',
              borderRadius: '6px',
              fontSize: '0.875rem',
              cursor: 'pointer',
              marginTop: 'auto',
            }}
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div style={{ color: 'var(--danger)', padding: '1rem', background: '#fef2f2', borderRadius: '6px', marginBottom: '1rem' }}>
          ⚠ {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="card" style={{ textAlign: 'center', padding: '3rem', color: 'var(--gray-500)' }}>
          Loading alerts...
        </div>
      )}

      {/* Alert List */}
      {!loading && !error && (
        <>
          {alerts.length === 0 ? (
            <div className="card" style={{ textAlign: 'center', padding: '3rem', color: 'var(--gray-500)' }}>
              No alerts found matching the current filters.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {alerts.map((alert) => (
                <AlertCard key={alert.id} alert={alert} />
              ))}
            </div>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div style={{ display: 'flex', justifyContent: 'center', gap: '0.5rem', marginTop: '1.5rem' }}>
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                style={{
                  padding: '0.5rem 1rem',
                  border: '1px solid var(--gray-300)',
                  borderRadius: '6px',
                  background: page === 1 ? 'var(--gray-100)' : 'white',
                  color: page === 1 ? 'var(--gray-400)' : 'var(--gray-700)',
                  cursor: page === 1 ? 'not-allowed' : 'pointer',
                }}
              >
                Previous
              </button>
              <span style={{ padding: '0.5rem 1rem', color: 'var(--gray-600)', fontSize: '0.875rem' }}>
                Page {page} of {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                style={{
                  padding: '0.5rem 1rem',
                  border: '1px solid var(--gray-300)',
                  borderRadius: '6px',
                  background: page === totalPages ? 'var(--gray-100)' : 'white',
                  color: page === totalPages ? 'var(--gray-400)' : 'var(--gray-700)',
                  cursor: page === totalPages ? 'not-allowed' : 'pointer',
                }}
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function AlertCard({ alert }: { alert: Alert }) {
  return (
    <a
      href={`/alerts/${alert.id}`}
      className="card"
      style={{
        display: 'block',
        padding: '1rem',
        textDecoration: 'none',
        color: 'inherit',
        transition: 'box-shadow 0.15s',
        cursor: 'pointer',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.1)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.boxShadow = 'none'
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem' }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
            <span style={{
              display: 'inline-block',
              padding: '0.125rem 0.5rem',
              borderRadius: '9999px',
              fontSize: '0.75rem',
              fontWeight: 600,
              color: 'white',
              background: SEVERITY_COLORS[alert.severity] || '#6b7280',
            }}>
              {alert.severity}
            </span>
            <span style={{
              display: 'inline-block',
              padding: '0.125rem 0.5rem',
              borderRadius: '9999px',
              fontSize: '0.75rem',
              fontWeight: 600,
              color: 'white',
              background: STATUS_COLORS[alert.status] || '#6b7280',
            }}>
              {alert.status.replace('_', ' ')}
            </span>
            {alert.risk_score && (
              <span style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>
                Risk: {alert.risk_score}
              </span>
            )}
          </div>
          <h3 style={{ fontSize: '1rem', fontWeight: 600, margin: 0, color: 'var(--gray-700)' }}>
            {alert.title}
          </h3>
          {alert.description && (
            <p style={{ fontSize: '0.875rem', color: 'var(--gray-500)', marginTop: '0.25rem', marginBottom: 0 }}>
              {alert.description.length > 200
                ? `${alert.description.substring(0, 200)}...`
                : alert.description}
            </p>
          )}
        </div>
        <div style={{ textAlign: 'right', flexShrink: 0 }}>
          <div style={{ fontSize: '0.75rem', color: 'var(--gray-400)' }}>
            {formatDate(alert.created_at)}
          </div>
        </div>
      </div>
    </a>
  )
}