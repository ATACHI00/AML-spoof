'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import {
  Alert,
  SEVERITY_COLORS,
  STATUS_COLORS,
  formatDate,
  getAlert,
  updateAlertStatus,
} from '../../api'

export default function AlertDetailPage() {
  const params = useParams()
  const router = useRouter()
  const alertId = params.id as string

  const [alert, setAlert] = useState<Alert | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Modal state
  const [showModal, setShowModal] = useState(false)
  const [actionStatus, setActionStatus] = useState<'closed' | 'escalated' | 'in_review'>('closed')
  const [comment, setComment] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  useEffect(() => {
    const fetchAlert = async () => {
      try {
        const data = await getAlert(alertId)
        setAlert(data)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load alert')
      } finally {
        setLoading(false)
      }
    }
    fetchAlert()
  }, [alertId])

  const handleStatusUpdate = async () => {
    if (!comment.trim()) return
    setSubmitting(true)
    setSubmitError(null)

    try {
      const result = await updateAlertStatus(alertId, actionStatus, comment)
      setAlert(result.alert)
      setShowModal(false)
      setComment('')
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Failed to update status')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="container" style={{ paddingTop: '2rem' }}>
        <div className="card" style={{ textAlign: 'center', padding: '3rem', color: 'var(--gray-500)' }}>
          Loading alert...
        </div>
      </div>
    )
  }

  if (error || !alert) {
    return (
      <div className="container" style={{ paddingTop: '2rem' }}>
        <div style={{ color: 'var(--danger)', padding: '1rem', background: '#fef2f2', borderRadius: '6px' }}>
          ⚠ {error || 'Alert not found'}
        </div>
        <button
          onClick={() => router.push('/alerts')}
          style={{
            marginTop: '1rem',
            padding: '0.5rem 1rem',
            background: 'var(--primary)',
            color: 'white',
            border: 'none',
            borderRadius: '6px',
            cursor: 'pointer',
          }}
        >
          ← Back to Alerts
        </button>
      </div>
    )
  }

  const canUpdate = alert.status !== 'closed'

  return (
    <div className="container" style={{ paddingTop: '2rem' }}>
      {/* Header */}
      <header style={{ marginBottom: '2rem' }}>
        <a
          href="/alerts"
          style={{ color: 'var(--primary)', textDecoration: 'none', fontSize: '0.875rem' }}
        >
          ← Back to Alerts
        </a>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginTop: '1rem' }}>
          <div>
            <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--gray-900)', margin: 0 }}>
              {alert.title}
            </h1>
            <p style={{ color: 'var(--gray-500)', fontSize: '0.875rem', marginTop: '0.25rem' }}>
              ID: {alert.id}
            </p>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            {canUpdate && (
              <>
                <ActionButton
                  label="In Review"
                  color="#f59e0b"
                  onClick={() => { setActionStatus('in_review'); setShowModal(true) }}
                />
                <ActionButton
                  label="Escalate"
                  color="#ef4444"
                  onClick={() => { setActionStatus('escalated'); setShowModal(true) }}
                />
                <ActionButton
                  label="Close"
                  color="#6b7280"
                  onClick={() => { setActionStatus('closed'); setShowModal(true) }}
                />
              </>
            )}
          </div>
        </div>
      </header>

      {/* Alert Details */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
        <div className="card">
          <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '1rem', color: 'var(--gray-700)' }}>
            Status & Classification
          </h2>
          <DetailRow label="Status" value={
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
          } />
          <DetailRow label="Severity" value={
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
          } />
          <DetailRow label="Risk Score" value={alert.risk_score || 'N/A'} />
          <DetailRow label="Created" value={formatDate(alert.created_at)} />
          <DetailRow label="Updated" value={formatDate(alert.updated_at)} />
        </div>

        <div className="card">
          <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '1rem', color: 'var(--gray-700)' }}>
            Related Entities
          </h2>
          <DetailRow label="Transaction ID" value={
            alert.transaction_id
              ? <code style={{ fontSize: '0.75rem' }}>{alert.transaction_id}</code>
              : 'N/A'
          } />
          <DetailRow label="Rule ID" value={
            alert.rule_id
              ? <code style={{ fontSize: '0.75rem' }}>{alert.rule_id}</code>
              : 'N/A'
          } />
          <DetailRow label="Case ID" value={
            alert.case_id
              ? <code style={{ fontSize: '0.75rem' }}>{alert.case_id}</code>
              : 'N/A'
          } />
        </div>
      </div>

      {/* Description */}
      {alert.description && (
        <div className="card" style={{ marginTop: '1.5rem' }}>
          <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.75rem', color: 'var(--gray-700)' }}>
            Description
          </h2>
          <p style={{ color: 'var(--gray-600)', lineHeight: 1.6, margin: 0, whiteSpace: 'pre-wrap' }}>
            {alert.description}
          </p>
        </div>
      )}

      {/* Status Update Modal */}
      {showModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0,0,0,0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
        }}
          onClick={() => setShowModal(false)}
        >
          <div
            className="card"
            style={{
              width: '100%',
              maxWidth: '480px',
              padding: '1.5rem',
              margin: '1rem',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 style={{ fontSize: '1.125rem', fontWeight: 600, marginBottom: '0.5rem', color: 'var(--gray-900)' }}>
              {actionStatus === 'closed' ? 'Close Alert' : actionStatus === 'escalated' ? 'Escalate Alert' : 'Move to In Review'}
            </h2>
            <p style={{ fontSize: '0.875rem', color: 'var(--gray-500)', marginBottom: '1rem' }}>
              {actionStatus === 'closed'
                ? 'Provide a reason for closing this alert.'
                : actionStatus === 'escalated'
                  ? 'Explain why this alert requires escalation.'
                  : 'Add a comment explaining why this alert is being reviewed.'}
            </p>

            <div style={{ marginBottom: '1rem' }}>
              <label style={{ fontSize: '0.875rem', fontWeight: 500, color: 'var(--gray-700)', display: 'block', marginBottom: '0.5rem' }}>
                Comment <span style={{ color: 'var(--danger)' }}>*</span>
              </label>
              <textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder="Enter your comment..."
                rows={4}
                style={{
                  width: '100%',
                  padding: '0.75rem',
                  borderRadius: '6px',
                  border: '1px solid var(--gray-300)',
                  fontSize: '0.875rem',
                  resize: 'vertical',
                  fontFamily: 'inherit',
                  boxSizing: 'border-box',
                }}
              />
            </div>

            {submitError && (
              <div style={{ color: 'var(--danger)', fontSize: '0.875rem', marginBottom: '1rem', padding: '0.5rem', background: '#fef2f2', borderRadius: '4px' }}>
                ⚠ {submitError}
              </div>
            )}

            <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
              <button
                onClick={() => { setShowModal(false); setComment(''); setSubmitError(null) }}
                style={{
                  padding: '0.5rem 1rem',
                  border: '1px solid var(--gray-300)',
                  borderRadius: '6px',
                  background: 'white',
                  color: 'var(--gray-700)',
                  cursor: 'pointer',
                  fontSize: '0.875rem',
                }}
              >
                Cancel
              </button>
              <button
                onClick={handleStatusUpdate}
                disabled={!comment.trim() || submitting}
                style={{
                  padding: '0.5rem 1rem',
                  border: 'none',
                  borderRadius: '6px',
                  background: !comment.trim() || submitting ? 'var(--gray-300)' : 'var(--primary)',
                  color: !comment.trim() || submitting ? 'var(--gray-500)' : 'white',
                  cursor: !comment.trim() || submitting ? 'not-allowed' : 'pointer',
                  fontSize: '0.875rem',
                  fontWeight: 500,
                }}
              >
                {submitting ? 'Updating...' : `Confirm ${actionStatus === 'closed' ? 'Close' : actionStatus === 'escalated' ? 'Escalation' : 'Review'}`}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function DetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div style={{
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      padding: '0.5rem 0',
      borderBottom: '1px solid var(--gray-100)',
    }}>
      <span style={{ fontSize: '0.875rem', color: 'var(--gray-500)' }}>{label}</span>
      <span style={{ fontSize: '0.875rem', color: 'var(--gray-800)', fontWeight: 500 }}>{value}</span>
    </div>
  )
}

function ActionButton({ label, color, onClick }: { label: string; color: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: '0.5rem 1rem',
        border: `1px solid ${color}`,
        borderRadius: '6px',
        background: 'white',
        color: color,
        cursor: 'pointer',
        fontSize: '0.875rem',
        fontWeight: 500,
        transition: 'all 0.15s',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = color
        e.currentTarget.style.color = 'white'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = 'white'
        e.currentTarget.style.color = color
      }}
    >
      {label}
    </button>
  )
}