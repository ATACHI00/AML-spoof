'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { formatDate } from '../api'

interface Exchange {
  id: string
  name: string
  country: string
  transactions: number
  volume: number
  riskScore: number
  status: 'active' | 'suspended' | 'under_review'
}

export default function ExchangesPage() {
  const [exchanges, setExchanges] = useState<Exchange[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Mock data for exchanges since API endpoint may not exist yet
    setExchanges([
      { id: '1', name: 'CryptoExchange Global', country: 'Cyprus', transactions: 1250, volume: 4500000, riskScore: 23, status: 'active' },
      { id: '2', name: 'Digital Assets Ltd', country: 'Belize', transactions: 890, volume: 2100000, riskScore: 35, status: 'active' },
      { id: '3', name: 'ChainLink Trading', country: 'Hong Kong', transactions: 670, volume: 1800000, riskScore: 48, status: 'under_review' },
      { id: '4', name: 'SafeHaven Exchange', country: 'Switzerland', transactions: 450, volume: 980000, riskScore: 12, status: 'active' },
    ])
    setLoading(false)
  }, [])

  return (
    <div className="container" style={{ paddingTop: '2rem' }}>
      <header style={{ marginBottom: '2rem' }}>
        <h1 style={{ fontSize: '1.875rem', fontWeight: 700, color: 'var(--gray-900)' }}>
          Exchanges
        </h1>
        <p style={{ color: 'var(--gray-900)', marginTop: '0.5rem' }}>
          Monitored cryptocurrency exchanges
        </p>
      </header>

      {loading && (
        <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--gray-500)' }}>
          Loading exchanges...
        </div>
      )}

      {!loading && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '1rem' }}>
          {exchanges.map((exchange) => (
            <div key={exchange.id} style={{
              background: 'white',
              borderRadius: '8px',
              padding: '1.25rem',
              border: '1px solid #e5e7eb',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '1rem' }}>
                <div>
                  <h3 style={{ fontWeight: 600, fontSize: '1.125rem', color: 'var(--gray-900)'}}>{exchange.name}</h3>
                  <p style={{ color: 'var(--gray-900)', fontSize: '0.875rem', margin: '0.25rem 0' }}>{exchange.country}</p>
                </div>
                <span style={{
                  display: 'inline-block',
                  padding: '0.25rem 0.5rem',
                  borderRadius: '4px',
                  fontSize: '0.75rem',
                  background: exchange.status === 'active' ? '#dcfce7' : exchange.status === 'under_review' ? '#fef3c7' : '#fee2e2',
                  color: exchange.status === 'active' ? '#166534' : exchange.status === 'under_review' ? '#92400e' : '#991b1b',
                }}>
                  {exchange.status}
                </span>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', fontSize: '0.875rem', color: 'var(--gray-900)' }}>
                <div>
                  <div style={{ color: 'var(--gray-900)', fontSize: '0.75rem' }}>Transactions</div>
                  <div style={{ fontWeight: 600 }}>{exchange.transactions.toLocaleString()}</div>
                </div>
                <div>
                  <div style={{ color: 'var(--gray-900)', fontSize: '0.75rem' }}>Volume</div>
                  <div style={{ fontWeight: 600 }}>{exchange.volume.toLocaleString()}</div>
                </div>
                <div style={{ gridColumn: '1 / -1' }}>
                  <div style={{ color: 'var(--gray-900)', fontSize: '0.75rem' }}>Risk Score</div>
                  <div style={{
                    fontWeight: 600,
                    color: exchange.riskScore >= 50 ? '#ef4444' : exchange.riskScore >= 30 ? '#f59e0b' : '#10b981'
                  }}>
                    {exchange.riskScore}/100
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <footer style={{ marginTop: '3rem', padding: '1rem 0', borderTop: '1px solid var(--gray-200)', color: 'var(--gray-900)', fontSize: '0.875rem' }}>
        <Link href="/" style={{ color: 'var(--grey-900)', textDecoration: 'none' }}>
          ← Back to Dashboard
        </Link>
      </footer>
    </div>
  )
}
