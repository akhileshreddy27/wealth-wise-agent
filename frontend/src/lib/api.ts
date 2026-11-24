// API client, shared types and number formatting.

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const isForm = body instanceof FormData
  const res = await fetch(`/api${path}`, {
    method,
    headers: body && !isForm ? { 'Content-Type': 'application/json' } : undefined,
    body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const j = await res.json()
      detail = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)
    } catch { /* not JSON */ }
    throw new ApiError(res.status, detail)
  }
  return res.status === 204 ? (undefined as T) : res.json()
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body),
  put: <T>(path: string, body: unknown) => request<T>('PUT', path, body),
  del: (path: string) => request<void>('DELETE', path),
}

// ---------- types ----------

export interface Health {
  ai_enabled: boolean
  model: string | null
  knowledge_search: 'hybrid' | 'keyword'
  market_updated_at: string | null
  has_profile: boolean
}

export interface Question { id: string; question: string; options: string[] }

export interface Profile {
  name: string; age: number; monthly_income: number; monthly_expenses: number; current_savings: number
  horizon_years: number; dependents: number; answers: Record<string, number>
  risk_score?: number; risk_category?: RiskCategory
}
export type RiskCategory = 'conservative' | 'moderate' | 'aggressive'

export interface FundPick {
  scheme_code: number; name: string; short_name: string; fund_house: string; category: string; peer_group: string
  score: number; peers: number; rank_in_category: number; reasons: string[]; cautions: string[]
  metrics: Record<string, number | null>
}
export interface StockPick {
  symbol: string; name: string; sector: string | null; price: number | null; score: number
  factors: Record<'value' | 'quality' | 'momentum' | 'low_vol', number>
  metrics: Record<string, number | null>; reasons: string[]; cautions: string[]
}
export interface FdQuote {
  bank: string; bank_type: string; rate: number; tenure_days: number; maturity_value: number; interest: number
  source_url: string | null
}
export interface Sleeve {
  sleeve: string; label: string; asset: 'equity' | 'debt' | 'fd' | 'liquid'; monthly: number
  funds: FundPick[]; stocks: StockPick[]
}
export interface Plan {
  risk: { score: number; category: RiskCategory }
  surplus: number
  emergency: { ok: boolean; target: number; current: number; shortfall: number; monthly_contribution: number; months_to_fill: number | null }
  allocation: { weights: Record<'equity' | 'debt' | 'fd' | 'liquid', number>; rationale: string[] }
  sleeves: Sleeve[]
  notes: string[]
  top_stocks: StockPick[]
  stocks_in_plan: boolean
  fd: { amount: number; tenure_days: number; best: FdQuote | null; safest: FdQuote | null; alternatives: FdQuote[]; as_of: string; notes: string[] }
  projection: { years: number; monthly_sip: number; expected_return: number; invested: number; future_value: number }
  market_updated_at: string | null
}

export interface Transaction { id: number; date: string; amount: number; kind: 'expense' | 'income'; category: string; note: string }
export interface CategoryMeta { label: string; bucket?: 'needs' | 'wants' | 'savings' }
export interface Categories { expense: Record<string, CategoryMeta>; income: Record<string, CategoryMeta> }

export interface CategoryRow {
  category: string; label: string; bucket: string; amount: number; share: number; budget: number | null; budget_used: number | null
}
export interface Summary {
  month: string; income: number; income_is_estimate: boolean; income_base: number; expense: number; invested: number
  net: number; savings_rate: number | null; categories: CategoryRow[]
  buckets: Record<'needs' | 'wants' | 'savings', number>; bucket_share: Record<'needs' | 'wants' | 'savings', number | null>
  trend: { month: string; income: number; expense: number }[]
}
export interface Insight {
  type: string; severity: 'danger' | 'warning' | 'info' | 'success'; title: string; detail: string; potential_saving: number
}
export interface SpendingResponse {
  months: string[]
  summary: Summary | null
  insights: { insights: Insight[]; potential_monthly_saving: number; recurring: { name: string; monthly_amount: number }[] } | null
}

export interface ModuleSummary { id: string; title: string; level: string; minutes: number; summary: string }
export interface Module extends ModuleSummary {
  markdown: string
  videos: { id: string; title: string; channel: string }[]
  video_query: string
  sources: { title: string; url: string }[]
  quiz: { q: string; options: string[]; answer: number; why: string }[]
}

export interface ChatMessage { role: 'user' | 'assistant'; content: string }
export interface Source { n: number; id: string; module_id: string; module_title: string; section: string }
export interface ChatReply { reply: string; sources: Source[]; tools_used: { name: string; args: Record<string, unknown> }[]; mode: 'ai' | 'search' }

// ---------- formatting ----------

const inrFmt = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })
export const inr = (n: number | null | undefined) => (n == null ? '–' : inrFmt.format(n))

/** ₹1.2 Cr, ₹4.5 L, ₹12,500 */
export function inrCompact(n: number | null | undefined) {
  if (n == null) return '–'
  const a = Math.abs(n)
  if (a >= 1e7) return `₹${(n / 1e7).toFixed(2)} Cr`
  if (a >= 1e5) return `₹${(n / 1e5).toFixed(2)} L`
  return inr(n)
}

export const pct = (n: number | null | undefined, digits = 1) => (n == null ? '–' : `${(n * 100).toFixed(digits)}%`)

export function monthLabel(month: string) {
  const [y, m] = month.split('-').map(Number)
  return new Date(y, m - 1, 1).toLocaleDateString('en-IN', { month: 'short', year: 'numeric' })
}

export function ago(iso: string | null) {
  if (!iso) return 'never'
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000)
  if (mins < 60) return `${mins} min ago`
  if (mins < 60 * 24) return `${Math.round(mins / 60)} h ago`
  return `${Math.round(mins / 1440)} days ago`
}
