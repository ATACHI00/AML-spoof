'use client'

import { useEffect, useState, useCallback } from 'react'
import Link from 'next/link'
import { formatDate, SEVERITY_COLORS, STATUS_COLORS } from '../api'

interface CryptoTransaction {
  id: string
  external_id: string
  source_account_id: string
  destination_account_id: string
  amount: string
  currency: string
  txn_timestamp: string
  channel: string | null
  status: string
  extra_data: any
  created_at: string
}

interface CryptoStats {
  total_transactions: number
  total_volume: number
  high_risk_count: number
  by_chain: Record<string, { count: number; volume: number }>
}

export default function CryptoPage() {
  const [transactions, setTransactions] = useState<CryptoTransaction[]>([])
  const [stats, setStats] = useState<CryptoStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedChain, setSelectedChain] = useState<string>('all')
  const [page, setPage] = useState(1)
  const [pageSize] = useState(20)

  useEffect(() => {
    fetchData()
  }, [page, selectedChain])

  async function fetchData() {
    setLoading(true)
    setError(null)
    try {
      const [txnsRes, statsRes] = await Promise.all([
        fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/transactions`),
        fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/compliance/stats`),
      ])

      if (txnsRes.ok) {
        const data = await txnsRes.json()
        let filtered = data.transactions || []
        if (selectedChain !== 'all') {
          filtered = filtered.filter((t: CryptoTransaction) => t.currency === selectedChain)
        }
        setTransactions(filtered.slice((page - 1) * pageSize, page * pageSize))
      }

      if (statsRes.ok) {
        const data = await statsRes.json()
        setStats(data)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load crypto data')
    } finally {
      setLoading(false)
    }
  }

  const chains = ['BTC', 'ETH', 'USDT', 'XMR']
  const chainColors: Record<string, string> = {
    BTC: '#f7931a',
    ETH: '#627eea',
    USDT: '#26a17b',
    XMR: '#ff6b35',
  }

  return (
    <div className="container" style={{ paddingTop: '2rem' }}>
      <header style={{ marginBottom: '2rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h1 style={{ fontSize: '1.875rem', fontWeight: 700, color: 'var(--gray-900)' }}>
              Crypto Monitoring
            </h1>
            <p style={{ color: 'var(--gray-500)', marginTop: '0.25rem' }}>
              Real-time blockchain transaction monitoring
            </p>
          </div>
          <a
            href="/"
            style={{
              color: 'var(--primary)',
              textDecoration: 'none',
              fontSize: '0.875rem',
            }}
          >
            ← Back to Dashboard
          </a>
        </div>
      </header>

      {/* Error */}
      {error && (
        <div style={{
          color: 'var(--danger)',
          padding: '1rem',
          background: '#fef2f2',
          borderRadius: '6px',
          marginBottom: '1rem',
        }}>
          ⚠ {error}
        </div>
      )}

      {/* Stats */}
      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
          <StatCard title="Total Transactions" value={stats.total_transactions} color="#3b82f6" />
          <StatCard title="High Risk Alerts" value={(stats.alerts_by_severity?.high || 0) + (stats.alerts_by_severity?.critical || 0)} color="#ef4444" />
          <StatCard title="Active Chains" value={chains.length} color="#10b981" />
        </div>
      )}

      {/* Chain Filters */}
      <div className="card" style={{ marginBottom: '1.5rem', padding: '1rem' }}>
        <div style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--gray-700)', marginBottom: '0.75rem' }}>
          Filter by Chain
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <button
            onClick={() => { setSelectedChain('all'); setPage(1) }}
            style={{
              padding: '0.5rem 1rem',
              border: selectedChain === 'all' ? '2px solid var(--primary)' : '1px solid var(--gray-300)',
              borderRadius: '9999px',
              background: selectedChain === 'all' ? 'var(--primary)' : 'white',
              color: selectedChain === 'all' ? 'white' : 'var(--gray-700)',
              fontWeight: 500,
              cursor: 'pointer',
              fontSize: '0.875rem',
            }}
          >
            All Chains
          </button>
          {chains.map((chain) => (
            <button
              key={chain}
              onClick={() => { setSelectedChain(chain); setPage(1) }}
              style={{
                padding: '0.5rem 1rem',
                border: selectedChain === chain ? '2px solid' : '1px solid var(--gray-300)',
                borderRadius: '9999px',
                background: selectedChain === chain ? chainColors[chain] : 'white',
                color: selectedChain === chain ? 'white' : '#6b7280',
                fontWeight: 500,
                cursor: 'pointer',
                fontSize: '0.875rem',
              }}
            >
              {chain}
            </button>
          ))}
        </div>
      </div>

      {/* Loading */}
      {loading && (
        <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--gray-500)' }}>
          Loading transactions...
        </div>
      )}

      {/* Transaction List */}
      {!loading && (
        <>
          {transactions.length === 0 ? (
            <div className="card" style={{ textAlign: 'center', padding: '3rem', color: 'var(--gray-500)' }}>
              No transactions found{selectedChain !== 'all' ? ` for ${selectedChain}` : ''}
            </div>
          ) : (
            <div className="card">
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
                  <thead>
                    <tr style={{ borderBottom: '2px solid var(--gray-200)' }}>
                      <th style={{ textAlign: 'left', padding: '0.75rem', fontWeight: 600, color: 'var(--gray-600)' }}>Time</th>
                      <th style={{ textAlign: 'left', padding: '0.75rem', fontWeight: 600, color: 'var(--gray-600)' }}>Chain</th>
                      <th style={{ textAlign: 'left', padding: '0.75rem', fontWeight: 600, color: 'var(--gray-600)' }}>Amount</th>
                      <th style={{ textAlign: 'left', padding: '0.75rem', fontWeight: 600, color: 'var(--gray-600)' }}>Source</th>
                      <th style={{ textAlign: 'left', padding: '0.75rem', fontWeight: 600, color: 'var(--gray-600)' }}>Dest</th>
                      <th style={{ textAlign: 'left', padding: '0.75rem', fontWeight: 600, color: 'var(--gray-600)' }}>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {transactions.map((txn) => (
                      <tr key={txn.id} style={{ borderBottom: '1px solid var(--gray-100)' }}>
                        <td style={{ padding: '0.75rem', color: 'var(--gray-600)' }}>{formatDate(txn.txn_timestamp)}</td>
                        <td style={{ padding: '0.75rem' }}>
                          <span style={{
                            display: 'inline-block',
                            padding: '0.125rem 0.5rem',
                            borderRadius: '4px',
                            fontSize: '0.75rem',
                            background: chainColors[txn.currency] || '#6b7280',
                            color: 'white',
                            fontWeight: 600,
                          }}>
                            {txn.currency}
                          </span>
                        </td>
                        <td style={{ padding: '0.75rem', fontWeight: 600 }}>
                          {Number(txn.amount).toLocaleString()} {txn.currency}
                        </td>
                        <td style={{ padding: '0.75rem', fontFamily: 'monospace', fontSize: '0.75rem' }}>
                          {txn.source_account_id?.substring(0, 8)}...
                        </td>
                        <td style={{ padding: '0.75rem', fontFamily: 'monospace', fontSize: '0.75rem' }}>
                          {txn.destination_account_id?.substring(0, 8)}...
                        </td>
                        <td style={{ padding: '0.75rem' }}>
                          <span style={{
                            display: 'inline-block',
                            padding: '0.125rem 0.5rem',
                            borderRadius: '9999px',
                            fontSize: '0.75rem',
                            fontWeight: 600,
                            color: 'white',
                            background: txn.status === 'cleared' ? '#10b981' : '#f59e0b',
                          }}>
                            {txn.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              <div style={{ display: 'flex', justifyContent: 'center', gap: '0.5rem', marginTop: '1rem', padding: '1rem' }}>
                <button
                  onClick={() => setPage(p => Math.max(1, p - 1))}
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
                  Page {page}
                </span>
                <button
                  onClick={() => setPage(p => p + 1)}
                  style={{
                    padding: '0.5rem 1rem',
                    border: '1px solid var(--gray-300)',
                    borderRadius: '6px',
                    background: 'white',
                    color: 'var(--gray-700)',
                    cursor: 'pointer',
                  }}
                >
                  Next
                </button>
              </div>
            </div>
          )}
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
      padding: '1.25rem',
      border: `1px solid ${color}20`,
      borderLeft: `4px solid ${color}`,
    }}>
      <div style={{ fontSize: '0.875rem', color: '#6b7280', marginBottom: '0.25rem' }}>{title}</div>
      <div style={{ fontSize: '2rem', fontWeight: 700, color }}>{value.toLocaleString()}</div>
    </div>
  )
}
