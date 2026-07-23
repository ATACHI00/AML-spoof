'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { formatDate } from '../api'

interface Wallet {
  id: string
  address: string
  chain: string
  label: string
  transactions: number
  balance: number
  riskScore: number
  status: 'verified' | 'suspicious' | 'blocked'
}

export default function WalletsPage() {
  const [wallets, setWallets] = useState<Wallet[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Mock data for wallets since API endpoint may not exist yet
    setWallets([
      { id: '1', address: '0x742d35Cc6634C0532925a3b844Bc454e4438f44e', chain: 'ETH', label: 'Main Wallet', transactions: 156, balance: 45000, riskScore: 18, status: 'verified' },
      { id: '2', address: 'bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh', chain: 'BTC', label: 'Cold Storage', transactions: 45, balance: 125000, riskScore: 5, status: 'verified' },
      { id: '3', address: '0x8ba1f109551bD432803012645Ac136ddd64DBA72', chain: 'ETH', label: 'Trading Wallet', transactions: 890, balance: 8900, riskScore: 42, status: 'suspicious' },
      { id: '4', address: 'tb1q6zv7l2w4v6k4q3m5n7p9r2s5t7u8v9w0x1y2z3', chain: 'BTC', label: 'Testnet Wallet', transactions: 23, balance: 5000, riskScore: 12, status: 'verified' },
    ])
    setLoading(false)
  }, [])

  return (
    <div className="container" style={{ paddingTop: '2rem' }}>
      <header style={{ marginBottom: '2rem' }}>
        <h1 style={{ fontSize: '1.875rem', fontWeight: 700, color: 'var(--gray-900)' }}>
          Wallets
        </h1>
        <p style={{ color: 'var(--gray-500)', marginTop: '0.5rem', color: 'var(--gray-900)' }}>
          Monitored cryptocurrency wallets
        </p>
      </header>

      {loading && (
        <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--gray-500)' }}>
          Loading wallets...
        </div>
      )}

      {!loading && (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
            <thead>
              <tr style={{ borderBottom: '2px solid var(--gray-200)' }}>
                <th style={{ textAlign: 'left', padding: '0.5rem', fontWeight: 600, color: 'var(--gray-900)' }}>Wallet</th>
                <th style={{ textAlign: 'left', padding: '0.5rem', fontWeight: 600, color: 'var(--gray-900)' }}>Chain</th>
                <th style={{ textAlign: 'left', padding: '0.5rem', fontWeight: 600, color: 'var(--gray-900)' }}>Label</th>
                <th style={{ textAlign: 'right', padding: '0.5rem', fontWeight: 600, color: 'var(--gray-900)' }}>Balance</th>
                <th style={{ textAlign: 'right', padding: '0.5rem', fontWeight: 600, color: 'var(--gray-900)' }}>Transactions</th>
                <th style={{ textAlign: 'right', padding: '0.5rem', fontWeight: 600, color: 'var(--gray-900)' }}>Risk Score</th>
                <th style={{ textAlign: 'left', padding: '0.5rem', fontWeight: 600, color: 'var(--gray-900)' }}>Status</th>
              </tr>
            </thead>
            <tbody style={{background: 'var(--gray-900)'}}>
              {wallets.map((wallet) => (
                <tr key={wallet.id} style={{ }}>
                  <td style={{ padding: '0.5rem', fontFamily: 'monospace', fontSize: '0.75rem' }}>
                    {wallet.address.substring(0, 10)}...{wallet.address.substring(wallet.address.length - 8)}
                  </td>
                  <td style={{ padding: '0.5rem' }}>
                    <span style={{
                      display: 'inline-block',
                      padding: '0.125rem 0.5rem',
                      borderRadius: '4px',
                      fontSize: '0.75rem',
                      background: getChainColor(wallet.chain),
                      color: 'var(--gray-900)',
                    }}>
                      {wallet.chain}
                    </span>
                  </td>
                  <td style={{ padding: '0.5rem', fontWeight: 500 }}>{wallet.label}</td>
                  <td style={{ padding: '0.5rem', textAlign: 'right', fontWeight: 500 }}>
                    {wallet.balance.toLocaleString()}
                  </td>
                  <td style={{ padding: '0.5rem', textAlign: 'right' }}>{wallet.transactions}</td>
                  <td style={{ padding: '0.5rem', textAlign: 'right', fontWeight: 500, color: wallet.riskScore >= 50 ? '#ef4444' : wallet.riskScore >= 30 ? '#f59e0b' : '#10b981' }}>
                    {wallet.riskScore}
                  </td>
                  <td style={{ padding: '0.5rem' }}>
                    <span style={{
                      display: 'inline-block',
                      padding: '0.125rem 0.5rem',
                      borderRadius: '4px',
                      fontSize: '0.75rem',
                      background: wallet.status === 'verified' ? '#dcfce7' : wallet.status === 'suspicious' ? '#fef3c7' : '#fee2e2',
                      color: wallet.status === 'verified' ? '#166534' : wallet.status === 'suspicious' ? '#92400e' : '#991b1b',
                    }}>
                      {wallet.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <footer style={{ marginTop: '3rem', padding: '1rem 0', borderTop: '1px solid var(--gray-200)', color: 'var(--gray-900)', fontSize: '0.875rem' }}>
        <Link href="/" style={{ color: 'var(--gray-900)', textDecoration: 'none' }}>
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
  }
  return colors[chain] || '#6b7280'
}
