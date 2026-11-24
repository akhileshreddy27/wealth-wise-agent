import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Card, cx, ErrorBox, Field, inputClass, Loading, PageHeader } from '../components/ui'
import { api } from '../lib/api'
import type { Profile, Question } from '../lib/api'
import { useApi } from '../lib/useApi'

const EMPTY: Profile = {
  name: '', age: 25, monthly_income: 60000, monthly_expenses: 35000, current_savings: 100000,
  horizon_years: 10, dependents: 0, answers: {},
}

const NUMBER_FIELDS: { key: keyof Profile; label: string; hint?: string; step?: number }[] = [
  { key: 'age', label: 'Age' },
  { key: 'monthly_income', label: 'Monthly take-home income (₹)', step: 1000 },
  { key: 'monthly_expenses', label: 'Monthly expenses (₹)', hint: 'Everything you spend, excluding SIPs', step: 1000 },
  { key: 'current_savings', label: 'Savings you can access (₹)', hint: 'Bank balance, FDs, liquid funds', step: 1000 },
  { key: 'horizon_years', label: 'Investment horizon (years)', hint: 'When will you need most of this money?' },
  { key: 'dependents', label: 'People who depend on your income' },
]

export default function ProfilePage({ onSaved }: { onSaved: () => void }) {
  const questions = useApi<Question[]>('/profile/questionnaire')
  const saved = useApi<Profile | null>('/profile')
  const [form, setForm] = useState<Profile>(EMPTY)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

  useEffect(() => { if (saved.data) setForm(saved.data) }, [saved.data])

  if (questions.loading || saved.loading) return <Loading />
  if (questions.error) return <ErrorBox error={questions.error} />

  const set = (key: keyof Profile, value: unknown) => setForm((f) => ({ ...f, [key]: value }))
  const unanswered = (questions.data ?? []).filter((q) => !form.answers[q.id]).length

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.put('/profile', form)
      onSaved()
      navigate('/plan')
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit}>
      <PageHeader
        title={saved.data ? 'Your profile' : 'Set up your profile'}
        subtitle="Your answers set your risk score (1–10), which drives every recommendation. Everything stays on your computer."
      />
      <div className="grid gap-6 lg:grid-cols-5">
        <Card title="Your finances" className="lg:col-span-2">
          <div className="space-y-4">
            <Field label="Name (optional)">
              <input className={inputClass} value={form.name} onChange={(e) => set('name', e.target.value)} />
            </Field>
            {NUMBER_FIELDS.map((f) => (
              <Field key={f.key} label={f.label} hint={f.hint}>
                <input type="number" min={0} step={f.step ?? 1} required className={inputClass}
                  value={form[f.key] as number} onChange={(e) => set(f.key, Number(e.target.value))} />
              </Field>
            ))}
          </div>
        </Card>

        <Card title="Risk questionnaire" subtitle="Pick the answer closest to how you'd really act." className="lg:col-span-3">
          <div className="space-y-6">
            {questions.data?.map((q, i) => (
              <fieldset key={q.id}>
                <legend className="mb-2 text-sm font-medium text-slate-800">{i + 1}. {q.question}</legend>
                <div className="grid gap-2 sm:grid-cols-2">
                  {q.options.map((label, idx) => {
                    const value = idx + 1
                    const checked = form.answers[q.id] === value
                    return (
                      <label key={label} className={cx('flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm transition',
                        checked ? 'border-brand-600 bg-brand-50 text-brand-900' : 'border-slate-200 hover:border-slate-300')}>
                        <input type="radio" name={q.id} className="accent-brand-700" checked={checked}
                          onChange={() => set('answers', { ...form.answers, [q.id]: value })} />
                        {label}
                      </label>
                    )
                  })}
                </div>
              </fieldset>
            ))}
          </div>
        </Card>
      </div>

      <div className="mt-6 flex items-center justify-end gap-4">
        {error && <span className="text-sm text-rose-600">{error}</span>}
        {unanswered > 0 && <span className="text-sm text-slate-500">{unanswered} question{unanswered > 1 ? 's' : ''} left</span>}
        <Button type="submit" busy={busy} disabled={unanswered > 0}>Save and see my plan</Button>
      </div>
    </form>
  )
}
