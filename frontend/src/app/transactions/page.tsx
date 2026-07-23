'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { formatDate, Transaction, listTransactions } from '../api'

export default function TransactionsPage() {
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchTransactions()
  }, [])

  async function fetchTransactions() {
    setLoading(true)
    setError(null)
    try {
      const data = await listTransactions({ page: 1, page_size: 50 })
      setTransactions(data.transactions || [])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch transactions')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="container" style={{ paddingTop: '2rem' }}>
      <header style={{ marginBottom: '2rem' }}>
        <h1 style={{ fontSize: '1.875rem', fontWeight: 700, color: 'var(--gray-900)' }}>
          Transactions
        </h1>
        <p style={{ color: 'var(--gray-500)', marginTop: '0.5rem' }}>
          All recorded transactions
        </p>
      </header>

      {error && (
        <div style={{
          color: 'var(--danger)',
          padding: '1rem',
          background: '#fef2f2',
          borderRadius: '6px',
          marginBottom: '1.5rem',
        }}>
          ⚠ Error: {error}
        </div>
      )}

      {loading && (
        <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--gray-500)' }}>
          Loading transactions...
        </div>
      )}

      {transactions.length > 0 && (
        <div className="card">
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
              <thead>
                <tr style={{ borderBottom: '2px solid var(--gray-200)' }}>
                  <th style={{ textAlign: 'left', padding: '0.5rem', fontWeight: 600, color: 'var(--gray-600)' }}>Time</th>
                  <th style={{ textAlign: 'left', padding: '0.5rem', fontWeight: 600, color: 'var(--gray-600)' }}>Chain</th>
                  <th style={{ textAlign: 'left', padding: '0.5rem', fontWeight: 600, color: 'var(--gray-600)' }}>Amount</th>
                  <th style={{ textAlign: 'left', padding: '0.5rem', fontWeight: 600, color: 'var(--gray-600)' }}>Source</th>
                  <th style={{ textAlign: 'left', padding: '0.5rem', fontWeight: 600, color: 'var(--gray-600)' }}>Dest</th>
                  <th style={{ textAlign: 'left', padding: '0.5rem', fontWeight: 600, color: 'var(--gray-600)' }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {transactions.map((txn) => (
                  <tr key={txn.id} style={{ borderBottom: '1px solid var(--gray-100)' }}>
                    <td style={{ padding: '0.5rem', color: 'var(--gray-600)' }}>{formatDate(txn.txn_timestamp)}</td>
                    <td style={{ padding: '0.5rem' }}>
                      <span style={{
                        display: 'inline-block',
                        padding: '0.125rem 0.5rem',
                        borderRadius: '4px',
                        fontSize: '0.75rem',
                        background: getChainColor(txn.currency),
                        color: 'white',
                      }}>
                        {txn.currency}
                      </span>
                    </td>
                    <td style={{ padding: '0.5rem', fontWeight: 500 }}>{Number(txn.amount).toLocaleString()}</td>
                    <td style={{ padding: '0.5rem', fontFamily: 'monospace', fontSize: '0.75rem' }}>
                      {txn.source_account_id
                        ? txn.source_account_id.substring(0, 12) + '...'
                        : txn.extra_data?.from_address?.substring(0, 12) + '...' ?? 'N/A'}
                    </td>
                    <td style={{ padding: '0.5rem', fontFamily: 'monospace', fontSize: '0.75rem' }}>
                      {txn.destination_account_id
                        ? txn.destination_account_id.substring(0, 12) + '...'
                        : txn.extra_data?.to_address?.substring(0, 12) + '...' ?? 'N/A'}
                    </td>
                    <td style={{ padding: '0.5rem' }}>
                      <span style={{
                        display: 'inline-block',
                        padding: '0.125rem 0.5rem',
                        borderRadius: '4px',
                        fontSize: '0.75rem',
                        background: txn.status === 'completed' ? '#dcfce7' : '#fef3c7',
                        color: txn.status === 'completed' ? '#166534' : '#92400e',
                      }}>
                        {txn.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {transactions.length === 0 && !loading && (
        <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--gray-500)' }}>
          No transactions found
        </div>
      )}

      <footer style={{ marginTop: '3rem', padding: '1rem 0', borderTop: '1px solid var(--gray-200)', color: 'var(--gray-400)', fontSize: '0.875rem' }}>
        <Link href="/" style={{ color: 'var(--primary)', textDecoration: 'none' }}>
          ← Back to Dashboard
        </Link>
      </footer>
    </div>
  )
}

function getChainColor(chain: string): string {
  const colors: Record<string, string> = {
    BTC: '#f7931a',
    ETH: '#627eea',
    USDT: '#26a17b',
    XMR: '#ff6b35',
    USD: '#10b981',
    EUR: '#3b82f6',
  }
  return colors[chain] || '#6b7280'
}
