import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Badge, Button, Card, cx, Empty, ErrorBox, Field, inputClass, Loading, PageHeader, Stat } from '../components/ui'
import { api, inr, inrCompact, monthLabel, pct } from '../lib/api'
import type { Categories, Insight, SpendingResponse, Summary, Transaction } from '../lib/api'
import { useApi } from '../lib/useApi'

const SEVERITY = {
  danger: { tone: 'red', label: 'Action' }, warning: { tone: 'amber', label: 'Watch' },
  info: { tone: 'blue', label: 'Tip' }, success: { tone: 'green', label: 'Good' },
} as const

export default function Expenses() {
  const [month, setMonth] = useState<string | null>(null)
  const spending = useApi<SpendingResponse>(`/expenses/summary${month ? `?month=${month}` : ''}`)
  const categories = useApi<Categories>('/expenses/categories')
  const currentMonth = spending.data?.summary?.month ?? null
  const txns = useApi<Transaction[]>(currentMonth ? `/transactions?month=${currentMonth}` : null)
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const reloadAll = async () => { await spending.reload(); await txns.reload() }

  async function run(label: string, fn: () => Promise<string>) {
    setBusy(label)
    setMessage(null)
    try {
      setMessage(await fn())
      setMonth(null)
      await reloadAll()
    } catch (e) {
      setMessage(`⚠️ ${(e as Error).message}`)
    } finally {
      setBusy(null)
    }
  }

  type ImportResult = { imported: number; duplicates: number; ai_categorised: number; errors?: string[] }
  const importText = (r: ImportResult) =>
    `Imported ${r.imported} transactions` + (r.duplicates ? `, skipped ${r.duplicates} duplicates` : '') +
    (r.ai_categorised ? `, ${r.ai_categorised} categorised by AI` : '') + (r.errors?.length ? `. ${r.errors.length} rows had errors.` : '.')

  const loadDemo = () => run('demo', async () => importText(await api.post<ImportResult>('/transactions/demo')))
  const importFile = (file: File) => run('import', async () => {
    const form = new FormData()
    form.append('file', file)
    return importText(await api.post<ImportResult>('/transactions/import', form))
  })
  const clearAll = () => {
    if (confirm('Delete all transactions? This cannot be undone.')) run('clear', async () => { await api.del('/transactions'); return 'All transactions deleted.' })
  }

  if (spending.loading && !spending.data) return <Loading />
  if (spending.error) return <ErrorBox error={spending.error} />
  const s = spending.data?.summary
  const months = spending.data?.months ?? []

  return (
    <>
      <PageHeader
        title="Expense tracker"
        subtitle="Track spending, set budgets and find savings. Investments (SIPs) count as saving, not spending."
        actions={<>
          {months.length > 0 && (
            <select className={cx(inputClass, 'w-auto')} value={currentMonth ?? ''} onChange={(e) => setMonth(e.target.value)}>
              {months.map((m) => <option key={m} value={m}>{monthLabel(m)}</option>)}
            </select>
          )}
          <Button variant="secondary" onClick={() => fileRef.current?.click()} busy={busy === 'import'}>Import CSV</Button>
          <Button onClick={() => setShowForm(!showForm)}>+ Add transaction</Button>
          <input ref={fileRef} type="file" accept=".csv" className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) importFile(f); e.target.value = '' }} />
        </>}
      />

      {message && <div className="mb-4 rounded-lg bg-slate-100 px-4 py-2.5 text-sm text-slate-700">{message}</div>}
      {showForm && categories.data && (
        <TransactionForm categories={categories.data} onDone={() => { setShowForm(false); setMonth(null); reloadAll() }} />
      )}

      {!s ? (
        <Empty title="No transactions yet">
          <p>Import a bank statement CSV (Date, Narration, Amount columns), add transactions by hand, or try it with six months of demo data.</p>
          <div className="mt-4"><Button onClick={loadDemo} busy={busy === 'demo'}>Load demo statement</Button></div>
        </Empty>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Income" value={inr(s.income_base)} hint={s.income_is_estimate ? 'From your profile (none recorded)' : monthLabel(s.month)} />
            <Stat label="Spent" value={inr(s.expense - s.invested)} hint={`${s.categories.filter((c) => c.amount > 0).length} categories`} />
            <Stat label="Invested" value={inr(s.invested)} hint="SIPs and investments" />
            <Stat label="Savings rate" value={pct(s.savings_rate, 0)} hint="Target: 20% or more"
              tone={s.savings_rate != null && s.savings_rate >= 0.2 ? 'good' : 'bad'} />
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-5">
            <InsightsCard insights={spending.data!.insights!.insights} potential={spending.data!.insights!.potential_monthly_saving} className="lg:col-span-3" />
            <RuleCard s={s} className="lg:col-span-2" />
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-5">
            <CategoryCard s={s} onBudgetsSaved={spending.reload} className="lg:col-span-3" />
            <Card title="Last 6 months" className="lg:col-span-2">
              <div className="h-64">
                <ResponsiveContainer>
                  <BarChart data={s.trend.map((t) => ({ ...t, label: monthLabel(t.month).split(' ')[0] }))}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                    <XAxis dataKey="label" tick={{ fontSize: 12 }} interval={0} />
                    <YAxis tickFormatter={(v) => inrCompact(v).replace('.00', '')} tick={{ fontSize: 11 }} width={60} />
                    <Tooltip formatter={(v) => inr(Number(v))} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Bar dataKey="income" name="Income" fill="var(--series-equity)" radius={[3, 3, 0, 0]} />
                    <Bar dataKey="expense" name="Outflow" fill="#94a3b8" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>
          </div>

          <Card title={`Transactions · ${monthLabel(s.month)}`} className="mt-6"
            actions={<Button variant="danger" onClick={clearAll} busy={busy === 'clear'}>Delete all</Button>}>
            {txns.loading && !txns.data ? <Loading /> : (
              <TransactionTable txns={txns.data ?? []} categories={categories.data} onChange={reloadAll} />
            )}
          </Card>
        </>
      )}
    </>
  )
}

function InsightsCard({ insights, potential, className }: { insights: Insight[]; potential: number; className?: string }) {
  return (
    <Card title="Savings insights" className={className}
      subtitle={potential > 0 ? `Up to ${inr(potential)}/month you could save` : 'How this month looks'}>
      {insights.length === 0 ? <p className="text-sm text-slate-500">Nothing to flag this month.</p> : (
        <ul className="space-y-3">
          {insights.map((i) => (
            <li key={i.title} className="flex items-start gap-3">
              <span className="w-14 shrink-0 pt-0.5"><Badge tone={SEVERITY[i.severity].tone}>{SEVERITY[i.severity].label}</Badge></span>
              <div>
                <div className="text-sm font-medium text-slate-900">{i.title}</div>
                <div className="text-sm text-slate-600">{i.detail}</div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

function RuleCard({ s, className }: { s: Summary; className?: string }) {
  const rows = [
    { key: 'needs', label: 'Needs', target: 0.5, color: 'bg-indigo-500' },
    { key: 'wants', label: 'Wants', target: 0.3, color: 'bg-amber-500' },
    { key: 'savings', label: 'Savings', target: 0.2, color: 'bg-brand-600' },
  ] as const
  return (
    <Card title="50/30/20 rule" subtitle="Share of income: needs ≤ 50%, wants ≤ 30%, savings ≥ 20%" className={className}>
      <div className="space-y-4">
        {rows.map((r) => {
          const share = s.bucket_share[r.key] ?? 0
          const off = r.key === 'savings' ? share < r.target : share > r.target
          return (
            <div key={r.key}>
              <div className="flex justify-between text-sm">
                <span className="font-medium">{r.label}</span>
                <span className={cx('tabular-nums', off ? 'text-rose-600' : 'text-slate-700')}>{pct(share, 0)} <span className="text-slate-400">/ {pct(r.target, 0)}</span></span>
              </div>
              <div className="relative mt-1 h-2.5 rounded-full bg-slate-100">
                <div className={cx('h-2.5 rounded-full', r.color)} style={{ width: `${Math.min(share, 1) * 100}%` }} />
                <div className="absolute top-[-3px] h-4 w-0.5 bg-slate-700" style={{ left: `${r.target * 100}%` }} title="Target" />
              </div>
              <div className="mt-0.5 text-xs text-slate-500">{inr(s.buckets[r.key])}</div>
            </div>
          )
        })}
      </div>
    </Card>
  )
}

function CategoryCard({ s, onBudgetsSaved, className }: { s: Summary; onBudgetsSaved: () => void; className?: string }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<Record<string, number>>({})
  useEffect(() => { setDraft(Object.fromEntries(s.categories.map((c) => [c.category, c.budget ?? 0]))) }, [s])
  const max = Math.max(...s.categories.map((c) => Math.max(c.amount, c.budget ?? 0)), 1)

  async function save() {
    await api.put('/budgets', draft)
    setEditing(false)
    onBudgetsSaved()
  }

  return (
    <Card title="Spending by category" className={className}
      actions={editing
        ? <div className="flex gap-2"><Button variant="ghost" onClick={() => setEditing(false)}>Cancel</Button><Button onClick={save}>Save budgets</Button></div>
        : <Button variant="secondary" onClick={() => setEditing(true)}>Edit budgets</Button>}>
      <div className="space-y-3">
        {s.categories.map((c) => (
          <div key={c.category}>
            <div className="flex items-center justify-between gap-3 text-sm">
              <span className="font-medium">{c.label} <span className="text-xs font-normal text-slate-400">{c.bucket}</span></span>
              {editing ? (
                <input type="number" min={0} step={500} className={cx(inputClass, 'w-28 py-1 text-right')} placeholder="No budget"
                  value={draft[c.category] || ''} onChange={(e) => setDraft({ ...draft, [c.category]: Number(e.target.value) })} />
              ) : (
                <span className="tabular-nums">{inr(c.amount)}{c.budget ? <span className="text-slate-400"> / {inr(c.budget)}</span> : null}</span>
              )}
            </div>
            <div className="relative mt-1 h-2 rounded-full bg-slate-100">
              <div className={cx('h-2 rounded-full', c.budget_used != null && c.budget_used > 1 ? 'bg-rose-500' : c.bucket === 'savings' ? 'bg-brand-600' : 'bg-slate-500')}
                style={{ width: `${(c.amount / max) * 100}%` }} />
              {c.budget ? <div className="absolute top-[-2px] h-3 w-0.5 bg-slate-800" style={{ left: `${(c.budget / max) * 100}%` }} /> : null}
            </div>
          </div>
        ))}
      </div>
      {editing && <p className="mt-3 text-xs text-slate-500">Set a monthly limit per category. Leave empty or 0 for no budget. Only categories with spending this month are shown.</p>}
    </Card>
  )
}

function TransactionTable({ txns, categories, onChange }: { txns: Transaction[]; categories: Categories | null; onChange: () => void }) {
  if (!txns.length) return <p className="text-sm text-slate-500">No transactions this month.</p>
  const label = (t: Transaction) => categories?.[t.kind][t.category]?.label ?? t.category

  async function recategorise(t: Transaction, category: string) {
    await api.put(`/transactions/${t.id}`, { ...t, category })
    onChange()
  }
  async function remove(t: Transaction) {
    await api.del(`/transactions/${t.id}`)
    onChange()
  }

  return (
    <div className="-mx-5 overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
            <th className="px-5 py-2 font-medium">Date</th><th className="py-2 font-medium">Description</th>
            <th className="py-2 font-medium">Category</th><th className="py-2 text-right font-medium">Amount</th><th className="px-5 py-2" />
          </tr>
        </thead>
        <tbody>
          {txns.map((t) => (
            <tr key={t.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
              <td className="whitespace-nowrap px-5 py-2 text-slate-500">{new Date(t.date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}</td>
              <td className="max-w-xs truncate py-2">{t.note || '–'}</td>
              <td className="py-2">
                {categories ? (
                  <select className="rounded border-0 bg-transparent py-0.5 pr-6 text-sm text-slate-700 hover:bg-slate-100" value={t.category}
                    onChange={(e) => recategorise(t, e.target.value)} title="Change category">
                    {Object.entries(categories[t.kind]).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                  </select>
                ) : label(t)}
              </td>
              <td className={cx('whitespace-nowrap py-2 text-right font-medium tabular-nums', t.kind === 'income' ? 'text-brand-700' : 'text-slate-900')}>
                {t.kind === 'income' ? '+' : '−'}{inr(t.amount)}
              </td>
              <td className="px-5 py-2 text-right">
                <button className="text-slate-400 hover:text-rose-600" onClick={() => remove(t)} title="Delete">✕</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function TransactionForm({ categories, onDone }: { categories: Categories; onDone: () => void }) {
  const [form, setForm] = useState({ date: new Date().toISOString().slice(0, 10), amount: '', kind: 'expense' as 'expense' | 'income', category: '', note: '' })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    try {
      await api.post('/transactions', { ...form, amount: Number(form.amount), category: form.category || null })
      onDone()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card className="mb-6">
      <form onSubmit={submit} className="grid items-end gap-3 sm:grid-cols-2 lg:grid-cols-6">
        <Field label="Type">
          <select className={inputClass} value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as 'expense' | 'income', category: '' })}>
            <option value="expense">Expense</option><option value="income">Income</option>
          </select>
        </Field>
        <Field label="Date"><input type="date" required className={inputClass} value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} /></Field>
        <Field label="Amount (₹)"><input type="number" min={1} required className={inputClass} value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></Field>
        <Field label="Description"><input className={inputClass} placeholder="e.g. Swiggy order" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} /></Field>
        <Field label="Category">
          <select className={inputClass} value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
            <option value="">Auto-detect</option>
            {Object.entries(categories[form.kind]).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
          </select>
        </Field>
        <Button type="submit" busy={busy}>Add</Button>
      </form>
      {error && <p className="mt-2 text-sm text-rose-600">{error}</p>}
    </Card>
  )
}
