import { useState } from 'react'
import Markdown from 'react-markdown'
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import { Badge, Button, ButtonLink, Card, cx, Empty, ErrorBox, Loading, PageHeader, Stat } from '../components/ui'
import { ago, api, inr, inrCompact, pct } from '../lib/api'
import type { FdQuote, FundPick, Plan, Sleeve, StockPick } from '../lib/api'
import { useApi } from '../lib/useApi'

const ASSET = {
  equity: { label: 'Equity', color: 'var(--series-equity)' },
  debt: { label: 'Debt funds', color: 'var(--series-debt)' },
  fd: { label: 'Fixed deposits', color: 'var(--series-fd)' },
  liquid: { label: 'Liquid', color: 'var(--series-liquid)' },
} as const

export function AllocationDonut({ weights }: { weights: Plan['allocation']['weights'] }) {
  const data = (Object.keys(ASSET) as (keyof typeof ASSET)[])
    .filter((k) => weights[k] > 0)
    .map((k) => ({ key: k, name: ASSET[k].label, value: Math.round(weights[k] * 100) }))
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
      <div className="size-40 shrink-0">
        <ResponsiveContainer>
          <PieChart>
            <Pie data={data} dataKey="value" innerRadius={45} outerRadius={75} paddingAngle={2} stroke="none">
              {data.map((d) => <Cell key={d.key} fill={ASSET[d.key].color} />)}
            </Pie>
            <Tooltip formatter={(v) => `${v}%`} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <ul className="min-w-40 flex-1 space-y-2 text-sm">
        {data.map((d) => (
          <li key={d.key} className="flex items-center gap-2">
            <span className="size-3 shrink-0 rounded-sm" style={{ background: ASSET[d.key].color }} />
            <span className="flex-1 text-slate-600">{d.name}</span>
            <span className="font-semibold tabular-nums">{d.value}%</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function PlanPage() {
  const plan = useApi<Plan>('/plan')
  const [refreshing, setRefreshing] = useState(false)
  const [refreshError, setRefreshError] = useState<string | null>(null)

  if (plan.loading && !plan.data) return <Loading label="Building your plan…" />
  if (plan.error?.message.includes('profile')) {
    return <Empty title="No profile yet"><p className="mb-4">Answer five questions and your plan appears here.</p><ButtonLink to="/profile">Set up profile</ButtonLink></Empty>
  }
  if (plan.error) return <ErrorBox error={plan.error} />
  const p = plan.data!

  async function refresh() {
    setRefreshing(true)
    setRefreshError(null)
    try {
      const r = await api.post<{ skipped?: string }>('/market/refresh')
      if (r.skipped) setRefreshError(`Already up to date: ${r.skipped}`)
      await plan.reload()
    } catch (e) {
      setRefreshError((e as Error).message)
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <>
      <PageHeader
        title="Your investment plan"
        subtitle={<>Built by Wealth Wise's scoring engine from live NSE and AMFI data · updated {ago(p.market_updated_at)}{refreshError && <span className="text-amber-700"> · {refreshError}</span>}</>}
        actions={<Button variant="secondary" busy={refreshing} onClick={refresh}>{refreshing ? 'Refreshing market data…' : 'Refresh market data'}</Button>}
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Risk score" value={`${p.risk.score}/10`} hint={<span className="capitalize">{p.risk.category}</span>} />
        <Stat label="Invest each month" value={inr(p.surplus)} hint="Your monthly surplus" />
        <Stat label="Emergency fund" value={p.emergency.ok ? 'Fully funded' : inr(p.emergency.shortfall)}
          hint={p.emergency.ok ? `${inr(p.emergency.target)} = 6 months of expenses` : `still needed · about ${p.emergency.months_to_fill} months to fill`}
          tone={p.emergency.ok ? 'good' : undefined} />
        <Stat label={`Projected in ${p.projection.years} yrs`} value={inrCompact(p.projection.future_value)}
          hint={`${inrCompact(p.projection.invested)} invested · ~${pct(p.projection.expected_return)} a year`} tone="good" />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-5">
        <Card title="Asset allocation" subtitle="Why your money is split this way" className="lg:col-span-2">
          <AllocationDonut weights={p.allocation.weights} />
          <ul className="mt-5 space-y-2 text-sm text-slate-600">
            {p.allocation.rationale.map((r) => <li key={r} className="flex gap-2"><span className="text-brand-600">•</span>{r}</li>)}
          </ul>
        </Card>
        <ExplainCard className="lg:col-span-3" />
      </div>

      <Card title="Monthly plan" subtitle="What to invest in each month, with the top-ranked funds for each part" className="mt-6">
        <div className="divide-y divide-slate-100">
          {p.sleeves.map((s) => <SleeveRow key={s.sleeve} sleeve={s} fd={s.sleeve === 'fd' ? p.fd.best : null} />)}
        </div>
        {p.notes.length > 0 && (
          <ul className="mt-4 space-y-1 rounded-lg bg-slate-50 p-3 text-sm text-slate-600">
            {p.notes.map((n) => <li key={n}>ℹ️ {n}</li>)}
          </ul>
        )}
      </Card>

      <div className="mt-6 grid gap-6 lg:grid-cols-5">
        <Card title="Top NIFTY 50 stocks for your profile" className="lg:col-span-3"
          subtitle={p.stocks_in_plan ? 'Your direct-stock money goes into the top picks (one stock per ~₹1,500 a month).' : 'For learning: your plan uses funds only, since direct stocks suit experienced investors.'}>
          <StockTable stocks={p.top_stocks} />
        </Card>
        <FdCard fd={p.fd} className="lg:col-span-2" />
      </div>
    </>
  )
}

function ExplainCard({ className }: { className?: string }) {
  const [text, setText] = useState<string | null>(null)
  const [mode, setMode] = useState<'ai' | 'rules' | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function explain() {
    setBusy(true)
    setError(null)
    try {
      const r = await api.post<{ text: string; mode: 'ai' | 'rules' }>('/plan/explain')
      setText(r.text)
      setMode(r.mode)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card title="Explain my plan" className={className}
      subtitle="The AI explainer agent puts the engine's numbers into plain words. It never makes up figures."
      actions={mode && <Badge tone={mode === 'ai' ? 'green' : 'slate'}>{mode === 'ai' ? 'Gemini' : 'Rule-based'}</Badge>}>
      {text ? (
        <div className="prose prose-sm prose-slate max-w-none"><Markdown>{text}</Markdown></div>
      ) : (
        <div className="flex flex-col items-start gap-3">
          <p className="text-sm text-slate-600">Get a short, personal walkthrough of why your plan looks the way it does and what to do this month.</p>
          <Button onClick={explain} busy={busy}>✨ Explain my plan</Button>
        </div>
      )}
      {error && <div className="mt-3"><ErrorBox error={error} /></div>}
    </Card>
  )
}

function SleeveRow({ sleeve, fd }: { sleeve: Sleeve; fd: FdQuote | null }) {
  const [open, setOpen] = useState(false)
  const color = ASSET[sleeve.asset].color
  return (
    <div className="py-3">
      <button className="flex w-full items-center gap-3 text-left" onClick={() => setOpen(!open)}>
        <span className="h-8 w-1 rounded-full" style={{ background: color }} />
        <div className="min-w-0 flex-1">
          <div className="font-medium text-slate-900">{sleeve.label}</div>
          <div className="truncate text-sm text-slate-500">
            {sleeve.funds.map((f) => f.short_name).join(' · ')}
            {sleeve.stocks.map((s) => s.symbol).join(' · ')}
            {fd && `${fd.bank} at ${fd.rate}%`}
          </div>
        </div>
        <div className="text-right">
          <div className="font-semibold tabular-nums">{inr(sleeve.monthly)}</div>
          <div className="text-xs text-slate-500">per month</div>
        </div>
        <svg className={cx('size-4 text-slate-400 transition', open && 'rotate-180')} viewBox="0 0 20 20" fill="currentColor"><path d="M5 7l5 6 5-6z" /></svg>
      </button>
      {open && (
        <div className="mt-3 grid gap-3 pl-4 md:grid-cols-2">
          {sleeve.funds.map((f) => <FundCard key={f.scheme_code} fund={f} />)}
          {sleeve.stocks.length > 0 && <p className="text-sm text-slate-600">About {inr(sleeve.monthly / sleeve.stocks.length)} a month for each of {sleeve.stocks.map((s) => s.symbol).join(', ')}. Buy whole shares as the money builds up. Scores and metrics are in the stocks card below.</p>}
          {fd && <p className="text-sm text-slate-600">Save this up and open an FD each year; see the FD card below for the rate and maturity value.</p>}
        </div>
      )}
    </div>
  )
}

function FundCard({ fund }: { fund: FundPick }) {
  const m = fund.metrics
  return (
    <div className="rounded-lg border border-slate-200 p-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-sm font-medium text-slate-900">{fund.short_name}</div>
          <div className="text-xs text-slate-500">{fund.category} · #{fund.rank_in_category} of {fund.peers} in {fund.peer_group}</div>
        </div>
        <Badge tone="green">{fund.score.toFixed(0)}/100</Badge>
      </div>
      <dl className="mt-2 grid grid-cols-3 gap-2 text-xs">
        <div><dt className="text-slate-500">3Y CAGR</dt><dd className="font-medium tabular-nums">{pct(m.cagr_3y)}</dd></div>
        <div><dt className="text-slate-500">Sharpe 3Y</dt><dd className="font-medium tabular-nums">{m.sharpe_3y?.toFixed(2) ?? '–'}</dd></div>
        <div><dt className="text-slate-500">Max fall</dt><dd className="font-medium tabular-nums">{pct(m.max_drawdown_3y)}</dd></div>
      </dl>
      {fund.reasons.map((r) => <p key={r} className="mt-1 text-xs text-brand-800">▲ {r}</p>)}
      {fund.cautions.map((c) => <p key={c} className="mt-1 text-xs text-amber-700">▼ {c}</p>)}
    </div>
  )
}

const FACTORS = [['quality', 'Quality'], ['value', 'Value'], ['momentum', 'Momentum'], ['low_vol', 'Low vol']] as const

function StockTable({ stocks }: { stocks: StockPick[] }) {
  if (!stocks.length) return <p className="text-sm text-slate-500">No stock data yet. Click "Refresh market data".</p>
  return (
    <div className="space-y-3">
      {stocks.map((s) => (
        <div key={s.symbol} className="rounded-lg border border-slate-200 p-3">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="font-medium text-slate-900">{s.symbol} <span className="font-normal text-slate-500">· {s.name}</span></div>
              <div className="text-xs text-slate-500">{s.sector} · ₹{s.price?.toLocaleString('en-IN')} · P/E {s.metrics.pe?.toFixed(1) ?? '–'} · ROE {pct(s.metrics.roe, 0)} · 1Y {pct(s.metrics.return_1y, 0)}</div>
            </div>
            <Badge tone="green">{s.score.toFixed(0)}/100</Badge>
          </div>
          <div className="mt-2 grid grid-cols-4 gap-2">
            {FACTORS.map(([key, label]) => (
              <div key={key}>
                <div className="flex justify-between text-[11px] text-slate-500"><span>{label}</span><span>{s.factors[key]}</span></div>
                <div className="mt-0.5 h-1.5 rounded-full bg-slate-100"><div className="h-1.5 rounded-full bg-brand-600" style={{ width: `${s.factors[key]}%` }} /></div>
              </div>
            ))}
          </div>
          {s.reasons.map((r) => <p key={r} className="mt-1.5 text-xs text-brand-800">▲ {r}</p>)}
          {s.cautions.map((c) => <p key={c} className="mt-1 text-xs text-amber-700">▼ {c}</p>)}
        </div>
      ))}
      <p className="text-xs text-slate-500">Score = weighted percentile of value (P/E, P/B), quality (ROE, debt, margin), momentum (6M/1Y return) and low volatility, with weights set by your risk profile. Max two stocks per sector.</p>
    </div>
  )
}

function FdCard({ fd, className }: { fd: Plan['fd']; className?: string }) {
  const best = fd.best
  return (
    <Card title="Best fixed deposit for you" className={className}
      subtitle={`${Math.round(fd.tenure_days / 365)}-year tenure · on ${inr(fd.amount)} · rates as of ${fd.as_of} (indicative)`}>
      {best ? (
        <>
          <div className="rounded-lg bg-amber-50 p-4">
            <div className="text-sm text-amber-900">{best.bank}</div>
            <div className="mt-1 text-3xl font-semibold tabular-nums text-amber-900">{best.rate}%</div>
            <div className="mt-1 text-sm text-amber-900">Matures to {inr(best.maturity_value)} ({inr(best.interest)} interest)</div>
          </div>
          {fd.safest && <p className="mt-3 text-sm text-slate-600">Bigger-bank option: <b>{fd.safest.bank}</b> at {fd.safest.rate}%.</p>}
          <table className="mt-3 w-full text-sm">
            <tbody>
              {fd.alternatives.map((q) => (
                <tr key={q.bank} className="border-t border-slate-100"><td className="py-1.5 text-slate-600">{q.bank}</td><td className="text-right tabular-nums">{q.rate}%</td></tr>
              ))}
            </tbody>
          </table>
          <ul className="mt-3 space-y-1 text-xs text-slate-500">{fd.notes.map((n) => <li key={n}>{n}</li>)}</ul>
        </>
      ) : <p className="text-sm text-slate-500">No FD rates for this tenure.</p>}
    </Card>
  )
}
