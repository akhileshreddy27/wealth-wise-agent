import { Link } from 'react-router-dom'
import { ButtonLink, Card, Empty, Loading, PageHeader, Stat } from '../components/ui'
import { inr, inrCompact, monthLabel, pct } from '../lib/api'
import type { Health, Plan, Profile, SpendingResponse } from '../lib/api'
import { useApi } from '../lib/useApi'
import { AllocationDonut } from './Plan'

const SEVERITY_DOT = { danger: 'bg-rose-500', warning: 'bg-amber-500', info: 'bg-sky-500', success: 'bg-brand-500' }

export default function Dashboard({ health }: { health: Health | null }) {
  const profile = useApi<Profile | null>('/profile')
  const hasProfile = !!profile.data
  const plan = useApi<Plan>(hasProfile ? '/plan' : null)
  const spending = useApi<SpendingResponse>('/expenses/summary')

  if (profile.loading) return <Loading />

  if (!hasProfile) {
    return (
      <>
        <PageHeader title="Welcome to Wealth Wise" subtitle="Your AI-powered personal finance assistant." />
        <div className="grid gap-4 md:grid-cols-3">
          {[
            ['Personal plan', 'A risk score from a 5-question quiz, then a monthly SIP plan with ranked funds, scored NIFTY 50 stocks and the best FD for you.'],
            ['Expense tracker', 'Import a bank statement or add spends. See budgets, the 50/30/20 split, subscriptions and spending spikes.'],
            ['Learn and ask', '13 short lessons with videos and quizzes, and an assistant that answers from them with live market data.'],
          ].map(([title, text]) => (
            <Card key={title} title={title}><p className="text-sm text-slate-600">{text}</p></Card>
          ))}
        </div>
        <div className="mt-6"><ButtonLink to="/profile">Get started: 2-minute profile →</ButtonLink></div>
      </>
    )
  }

  const p = plan.data
  const s = spending.data?.summary
  const insights = spending.data?.insights?.insights ?? []

  return (
    <>
      <PageHeader title={`Hi${profile.data?.name ? `, ${profile.data.name}` : ''}`} subtitle="Here's where your money stands." />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Risk profile" value={p ? `${p.risk.score}/10` : '–'} hint={<span className="capitalize">{p?.risk.category}</span>} />
        <Stat label="Monthly surplus" value={p ? inr(p.surplus) : '–'} hint="Income minus expenses (profile)" />
        <Stat label="Monthly SIPs" value={p ? inr(p.projection.monthly_sip) : '–'}
          hint={p && p.emergency.monthly_contribution ? `+ ${inr(p.emergency.monthly_contribution)} to emergency fund` : 'Emergency fund is full'} />
        <Stat label={`In ${p?.projection.years ?? '–'} years`} value={p ? inrCompact(p.projection.future_value) : '–'}
          hint={p ? `at ~${pct(p.projection.expected_return)} a year (not guaranteed)` : undefined} tone="good" />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card title="Your asset allocation" actions={<Link to="/plan" className="text-sm font-medium text-brand-700 hover:underline">Full plan →</Link>}>
          {p ? <AllocationDonut weights={p.allocation.weights} /> : <Loading />}
        </Card>

        <Card title={s ? `Spending: ${monthLabel(s.month)}` : 'Spending'}
          actions={<Link to="/expenses" className="text-sm font-medium text-brand-700 hover:underline">Expenses →</Link>}>
          {!s ? (
            <Empty title="No transactions yet">Load the demo statement or import your own on the <Link className="text-brand-700 underline" to="/expenses">Expenses</Link> page.</Empty>
          ) : (
            <>
              <div className="grid grid-cols-3 gap-3 text-sm">
                <div><div className="text-slate-500">Income</div><div className="font-semibold tabular-nums">{inr(s.income_base)}</div></div>
                <div><div className="text-slate-500">Spent</div><div className="font-semibold tabular-nums">{inr(s.expense - s.invested)}</div></div>
                <div><div className="text-slate-500">Savings rate</div><div className="font-semibold tabular-nums text-brand-700">{pct(s.savings_rate, 0)}</div></div>
              </div>
              <ul className="mt-4 space-y-2">
                {insights.slice(0, 4).map((i) => (
                  <li key={i.title} className="flex items-start gap-2 text-sm">
                    <span className={`mt-1.5 size-2 shrink-0 rounded-full ${SEVERITY_DOT[i.severity]}`} />
                    <span>{i.title}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </Card>
      </div>

      <div className="mt-6 grid gap-4 md:grid-cols-2">
        <Link to="/assistant" className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition hover:border-brand-600">
          <div className="font-semibold text-slate-900">Ask the assistant →</div>
          <p className="mt-1 text-sm text-slate-500">
            "Is my emergency fund enough?" · "What's Parag Parikh Flexi Cap's NAV today?" · "How much SIP for ₹20 lakh in 8 years?"
          </p>
          {health && !health.ai_enabled && <p className="mt-2 text-xs text-amber-700">AI is off: add GEMINI_API_KEY to backend/.env for full answers.</p>}
        </Link>
        <Link to="/learn" className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition hover:border-brand-600">
          <div className="font-semibold text-slate-900">Learn the basics →</div>
          <p className="mt-1 text-sm text-slate-500">13 short lessons with videos and quizzes: SIPs, index funds, FDs, tax, risk metrics and more.</p>
        </Link>
      </div>
    </>
  )
}
