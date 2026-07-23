/** API types for transactions */

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
  const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
  const API_KEY = process.env.NEXT_PUBLIC_API_KEY || 'dev-api-key-1'

  const res = await fetch(`${API_URL}/api/v1/transactions?page=${page}&page_size=${pageSize}`, {
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': API_KEY,
    },
  })

  if (!res.ok) {
    const body = await res.text()
    throw new Error(`API error ${res.status}: ${body}`)
  }

  return res.json()
}
