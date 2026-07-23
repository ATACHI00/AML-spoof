import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'AML Monitor — Transaction Monitoring Platform',
  description: 'Anti-Money Laundering transaction monitoring for fintech companies',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}