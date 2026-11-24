import { Link } from 'react-router-dom'
import { Badge, ErrorBox, Loading, PageHeader } from '../components/ui'
import type { ModuleSummary } from '../lib/api'
import { loadProgress } from '../lib/progress'
import { useApi } from '../lib/useApi'

const LEVEL_TONE = { Beginner: 'green', Intermediate: 'blue', Advanced: 'amber' } as const

export default function Learn() {
  const modules = useApi<ModuleSummary[]>('/learn/modules')
  const progress = loadProgress()

  if (modules.loading) return <Loading />
  if (modules.error) return <ErrorBox error={modules.error} />
  const done = modules.data!.filter((m) => (progress[m.id] ?? 0) >= 0.5).length

  return (
    <>
      <PageHeader title="Learn" subtitle={`Short lessons with videos and quizzes. These lessons are also what the assistant answers from. ${done}/${modules.data!.length} completed.`} />
      <div className="mb-6 h-2 rounded-full bg-slate-200">
        <div className="h-2 rounded-full bg-brand-600 transition-all" style={{ width: `${(done / modules.data!.length) * 100}%` }} />
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {modules.data!.map((m, i) => {
          const score = progress[m.id]
          return (
            <Link key={m.id} to={`/learn/${m.id}`}
              className="group flex flex-col rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition hover:border-brand-600">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-slate-400">Lesson {i + 1}</span>
                {score != null && <Badge tone={score >= 0.5 ? 'green' : 'amber'}>Quiz {Math.round(score * 100)}%</Badge>}
              </div>
              <h3 className="mt-2 font-semibold text-slate-900 group-hover:text-brand-800">{m.title}</h3>
              <p className="mt-1 flex-1 text-sm text-slate-600">{m.summary}</p>
              <div className="mt-4 flex items-center gap-2 text-xs text-slate-500">
                <Badge tone={LEVEL_TONE[m.level as keyof typeof LEVEL_TONE] ?? 'slate'}>{m.level}</Badge>
                {m.minutes} min read · video
              </div>
            </Link>
          )
        })}
      </div>
    </>
  )
}
