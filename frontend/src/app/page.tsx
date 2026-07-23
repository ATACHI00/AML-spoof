'use client'

import { useEffect, useState, useCallback } from 'react'
import Link from 'next/link'
import {
  Alert,
  AlertFilters,
  SEVERITY_COLORS,
  STATUS_COLORS,
  formatDate,
  listAlerts,
  ComplianceStats,
  getComplianceStats,
  Transaction,
  listTransactions,
} from './api'

// Crypto activity data type
interface CryptoActivity {
  chain: string
  transactions: number
  volume: number
  alerts: number
  riskScore: number
}

// High risk alerts data
interface HighRiskAlert {
  id: string
  title: string
  severity: string
  riskScore: string | null
  description: string | null
  created_at: string
  transaction_id: string | null
}

export default function Home() {
  const [health, setHealth] = useState<any>(null)
  const [stats, setStats] = useState<ComplianceStats | null>(null)
  const [cryptoStats, setCryptoStats] = useState<CryptoActivity[]>([])
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 30000)
    return () => clearInterval(interval)
  }, [])

  async function fetchData() {
    setLoading(true)
    setError(null)
    try {
      const [healthRes, statsRes, cryptoRes, txnsRes] = await Promise.all([
        fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/health`),
        getComplianceStats(),
        fetchCryptoStats(),
        fetchTransactions(),
      ])

      if (healthRes.ok) {
        setHealth(await healthRes.json())
      }
      setStats(statsRes)
      setCryptoStats(cryptoRes)
      setTransactions(txnsRes)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to connect')
    } finally {
      setLoading(false)
    }
  }

  async function fetchCryptoStats(): Promise<CryptoActivity[]> {
    try {
      const txns = await fetchTransactions()
      const chains = ['BTC', 'ETH', 'USDT', 'XMR']
      return chains.map(chain => {
        const chainTxns = txns.filter((t: Transaction) => t.currency === chain)
        return {
          chain,
          transactions: chainTxns.length,
          volume: chainTxns.reduce((sum: number, t: Transaction) => sum + Number(t.amount), 0),
          alerts: 0,
          riskScore: 0,
        }
      })
    } catch {
      return [
        { chain: 'BTC', transactions: 0, volume: 0, alerts: 0, riskScore: 0 },
        { chain: 'ETH', transactions: 0, volume: 0, alerts: 0, riskScore: 0 },
        { chain: 'USDT', transactions: 0, volume: 0, alerts: 0, riskScore: 0 },
        { chain: 'XMR', transactions: 0, volume: 0, alerts: 0, riskScore: 0 },
      ]
    }
  }

  async function fetchTransactions(): Promise<Transaction[]> {
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/transactions`)
      if (!res.ok) throw new Error('Failed to fetch transactions')
      const data = await res.json()
      return data.transactions || []
    } catch {
      return []
    }
  }

  return (
    <div className="container" style={{ paddingTop: '2rem' }}>
      <header style={{ marginBottom: '2rem' }}>
        <h1 style={{ fontSize: '1.875rem', fontWeight: 700, color: 'var(--gray-900)' }}>
          AML Monitor Dashboard
        </h1>
        <p style={{ color: 'var(--gray-900)', marginTop: '0.5rem' }}>
          Anti-Money Laundering Transaction Monitoring Platform
        </p>
      </header>

      {/* Error */}
      {error && (
        <div style={{
          color: 'var(--danger)',
          padding: '1rem',
          background: '#fef2f2',
          borderRadius: '6px',
          marginBottom: '1.5rem',
        }}>
          ⚠ Connection error: {error}
        </div>
      )}

      {loading && !health && (
        <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--gray-900)' }}>
          Loading dashboard...
        </div>
      )}

      {/* System Status */}
      {health && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 600, marginBottom: '1rem' }}>
            System Status
          </h2>
          <div style={{ display: 'grid', gap: '0.75rem' }}>
            <StatusRow label="API Status" value={health.status} />
            <StatusRow label="Version" value={health.version} />
            <StatusRow label="Database" value={health.database || 'unknown'} />
            <StatusRow label="Redis" value={health.redis || 'unknown'} />
            <StatusRow label="Celery" value={health.celery || 'unknown'} />
          </div>
        </div>
      )}

      {/* Stats Cards */}
      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
          <StatCard title="Total Alerts" value={stats.total_alerts} color="#3b82f6" />
          <StatCard title="Open Cases" value={stats.open_cases} color="#f59e0b" />
          <StatCard title="Transactions" value={stats.total_transactions} color="#10b981" />
          <StatCard title="High Risk Alerts" value={(stats.alerts_by_severity?.high || 0) + (stats.alerts_by_severity?.critical || 0)} color="#ef4444" />
        </div>
      )}

      {/* Crypto Monitoring */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 600 }}>Crypto Monitoring</h2>
          <Link href="/crypto" style={{ fontSize: '0.875rem', color: 'var(--primary)', textDecoration: 'none' }}>
            View All →
          </Link>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', color: 'var(--gray-900)' }}>
          {cryptoStats.map((item) => (
            <CryptoStatCard
              key={item.chain}
              chain={item.chain}
              transactions={item.transactions}
              volume={item.volume}
              riskScore={item.riskScore}
            />
          ))}
        </div>
      </div>

      {/* Latest Transactions */}
      {transactions.length > 0 && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 600 }}>Latest Transactions</h2>
            <Link href="/transactions" style={{ fontSize: '0.875rem', color: 'var(--primary)', textDecoration: 'none' }}>
              View All →
            </Link>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
              <thead>
                <tr style={{ borderBottom: '2px solid var(--gray-900)' }}>
                  <th style={{ textAlign: 'left', padding: '0.5rem', fontWeight: 600, color: 'var(--gray-600)' }}>Time</th>
                  <th style={{ textAlign: 'left', padding: '0.5rem', fontWeight: 600, color: 'var(--gray-600)' }}>Chain</th>
                  <th style={{ textAlign: 'left', padding: '0.5rem', fontWeight: 600, color: 'var(--gray-600)' }}>Amount</th>
                  <th style={{ textAlign: 'left', padding: '0.5rem', fontWeight: 600, color: 'var(--gray-600)' }}>Source</th>
                  <th style={{ textAlign: 'left', padding: '0.5rem', fontWeight: 600, color: 'var(--gray-900)' }}>Dest</th>
                </tr>
              </thead>
              <tbody>
                {transactions.slice(0, 10).map((txn) => (
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
                      {txn.source_account_id?.substring(0, 8)}...
                    </td>
                    <td style={{ padding: '0.5rem', fontFamily: 'monospace', fontSize: '0.75rem' }}>
                      {txn.destination_account_id?.substring(0, 8)}...
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Quick Actions */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <h2 style={{ fontSize: '1.25rem', fontWeight: 600, marginBottom: '1rem' }}>
          Quick Actions
        </h2>
        <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
          <LinkButton href="/alerts" label="View Alerts" />
          <LinkButton href="/compliance" label="Compliance Dashboard" />
          <LinkButton href="/transactions" label="Transactions" />
          <LinkButton href="/exchanges" label="Exchanges" />
          <LinkButton href="/wallets" label="Wallets" />
        </div>
      </div>

      <footer style={{ marginTop: '3rem', padding: '1rem 0', borderTop: '1px solid var(--gray-200)', color: 'var(--gray-400)', fontSize: '0.875rem' }}>
        AML Monitor v{health?.version || '0.1.0'} — Automated Blockchain Monitoring Active
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

function StatusRow({ label, value }: { label: string; value: string }) {
  const isOk = value === 'connected' || value === 'ok'
  const isDegraded = value?.startsWith('error') || value === 'no workers'

  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.5rem 0', borderBottom: '1px solid var(--gray-100)' }}>
      <span style={{ color: 'var(--gray-600)' }}>{label}</span>
      <span style={{
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
        color: isOk ? 'var(--success)' : isDegraded ? 'var(--danger)' : 'var(--gray-500)',
        fontWeight: 500,
      }}>
        <span style={{
          width: 8,
          height: 8,
          borderRadius: '50%',
          background: isOk ? 'var(--success)' : isDegraded ? 'var(--danger)' : 'var(--gray-400)',
          display: 'inline-block',
        }} />
        {value}
      </span>
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

function CryptoStatCard({ chain, transactions, volume, riskScore }: { chain: string; transactions: number; volume: number; riskScore: number }) {
  const colors = {
    BTC: '#f7931a',
    ETH: '#627eea',
    USDT: '#26a17b',
    XMR: '#ff6b35',
  }

  return (
    <div style={{
      background: 'white',
      borderRadius: '8px',
      padding: '1rem',
      border: '1px solid #e5e7eb',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
        <div style={{
          width: 32,
          height: 32,
          borderRadius: '50%',
          background: colors[chain as keyof typeof colors] || '#6b7280',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'white',
          fontWeight: 700,
          fontSize: '0.875rem',
        }}>
          {chain[0]}
        </div>
        <div>
          <div style={{ fontWeight: 600, fontSize: '1rem' }}>{chain}</div>
          <div style={{ fontSize: '0.75rem', color: '#6b7280' }}>
            Risk: <span style={{ color: riskScore >= 50 ? '#ef4444' : '#10b981' }}>{riskScore.toFixed(1)}</span>
          </div>
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', fontSize: '0.875rem' }}>
        <div>
          <div style={{ color: '#6b7280', fontSize: '0.75rem' }}>Transactions</div>
          <div style={{ fontWeight: 600 }}>{transactions.toLocaleString()}</div>
        </div>
        <div>
          <div style={{ color: '#6b7280', fontSize: '0.75rem' }}>Volume</div>
          <div style={{ fontWeight: 600 }}>{volume.toLocaleString()}</div>
        </div>
      </div>
    </div>
  )
}

function LinkButton({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      style={{
        display: 'inline-block',
        padding: '0.5rem 1rem',
        background: 'var(--primary)',
        color: 'white',
        borderRadius: '6px',
        fontSize: '0.875rem',
        fontWeight: 500,
        textDecoration: 'none',
      }}
    >
      {label} →
    </a>
  )
}
