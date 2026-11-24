import { useEffect, useState } from 'react'
import Markdown from 'react-markdown'
import { Link, useLocation, useParams } from 'react-router-dom'
import remarkGfm from 'remark-gfm'
import { Badge, Button, Card, cx, ErrorBox, Loading } from '../components/ui'
import type { Module } from '../lib/api'
import { saveScore } from '../lib/progress'
import { useApi } from '../lib/useApi'

const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')

export default function LearnModule() {
  const { id } = useParams()
  const mod = useApi<Module>(`/learn/modules/${id}`)
  const { hash } = useLocation()
  useEffect(() => { // jump to a cited section (links from the assistant end in #section-slug)
    if (mod.data && hash) document.getElementById(hash.slice(1))?.scrollIntoView({ behavior: 'smooth' })
  }, [mod.data, hash])
  if (mod.loading) return <Loading />
  if (mod.error) return <ErrorBox error={mod.error} />
  const m = mod.data!
  const body = m.markdown.split('\n').slice(1).join('\n') // the title is rendered separately

  return (
    <div className="mx-auto max-w-3xl">
      <Link to="/learn" className="text-sm text-brand-700 hover:underline">← All lessons</Link>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight text-slate-900">{m.title}</h1>
      <div className="mt-2 flex items-center gap-2 text-sm text-slate-500"><Badge tone="green">{m.level}</Badge> {m.minutes} min read</div>

      {m.videos.length > 0 && (
        <div className={cx('mt-6 grid gap-4', m.videos.length > 1 && 'sm:grid-cols-2')}>
          {m.videos.map((v) => <Video key={v.id} video={v} />)}
        </div>
      )}
      <a className="mt-2 inline-block text-xs text-slate-500 hover:text-brand-700"
        href={`https://www.youtube.com/results?search_query=${encodeURIComponent(m.video_query)}`} target="_blank" rel="noreferrer">
        More videos on this topic ↗
      </a>

      <article className="prose prose-slate mt-6 max-w-none prose-headings:scroll-mt-6 prose-h2:text-xl">
        <Markdown remarkPlugins={[remarkGfm]} components={{
          h2: ({ children }) => <h2 id={slug(String(children))}>{children}</h2>,
        }}>{body}</Markdown>
      </article>

      {m.sources.length > 0 && (
        <p className="mt-6 text-sm text-slate-500">
          Sources: {m.sources.map((s, i) => <span key={s.url}>{i > 0 && ' · '}<a className="text-brand-700 hover:underline" href={s.url} target="_blank" rel="noreferrer">{s.title}</a></span>)}
        </p>
      )}

      <Quiz module={m} />
    </div>
  )
}

function Quiz({ module: m }: { module: Module }) {
  const [picked, setPicked] = useState<Record<number, number>>({})
  const [submitted, setSubmitted] = useState(false)
  const correct = m.quiz.filter((q, i) => picked[i] === q.answer).length

  function submit() {
    setSubmitted(true)
    saveScore(m.id, correct / m.quiz.length)
  }

  return (
    <Card title="Quick quiz" subtitle="Check what stuck. Your best score is saved in this browser." className="mt-8">
      <div className="space-y-5">
        {m.quiz.map((q, i) => (
          <div key={q.q}>
            <div className="text-sm font-medium text-slate-900">{i + 1}. {q.q}</div>
            <div className="mt-2 grid gap-2">
              {q.options.map((opt, j) => {
                const chosen = picked[i] === j
                const state = submitted ? (j === q.answer ? 'right' : chosen ? 'wrong' : 'idle') : chosen ? 'chosen' : 'idle'
                return (
                  <button key={opt} disabled={submitted} onClick={() => setPicked({ ...picked, [i]: j })}
                    className={cx('rounded-lg border px-3 py-2 text-left text-sm transition', {
                      idle: 'border-slate-200 hover:border-slate-300', chosen: 'border-brand-600 bg-brand-50',
                      right: 'border-brand-600 bg-brand-50 text-brand-900', wrong: 'border-rose-300 bg-rose-50 text-rose-800',
                    }[state])}>
                    {opt}
                  </button>
                )
              })}
            </div>
            {submitted && <p className="mt-2 text-sm text-slate-600">💡 {q.why}</p>}
          </div>
        ))}
      </div>
      <div className="mt-5 flex items-center gap-4">
        {submitted ? (
          <>
            <span className="font-medium">You got {correct} of {m.quiz.length}.</span>
            <Button variant="secondary" onClick={() => { setPicked({}); setSubmitted(false) }}>Try again</Button>
          </>
        ) : (
          <Button onClick={submit} disabled={Object.keys(picked).length < m.quiz.length}>Check answers</Button>
        )}
      </div>
    </Card>
  )
}

/** Click-to-play: shows the thumbnail and only loads the YouTube player when clicked. */
function Video({ video }: { video: Module['videos'][number] }) {
  const [playing, setPlaying] = useState(false)
  return (
    <figure>
      <div className="relative aspect-video overflow-hidden rounded-xl bg-slate-800">
        {playing ? (
          <iframe className="size-full" src={`https://www.youtube-nocookie.com/embed/${video.id}?autoplay=1`} title={video.title}
            allow="accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture" allowFullScreen />
        ) : (
          <button className="group size-full" onClick={() => setPlaying(true)} aria-label={`Play: ${video.title}`}>
            <img src={`https://i.ytimg.com/vi/${video.id}/hqdefault.jpg`} alt="" className="size-full object-cover opacity-90 transition group-hover:opacity-100" />
            <span className="absolute inset-0 m-auto flex size-14 items-center justify-center rounded-full bg-black/70 text-white transition group-hover:bg-red-600">
              <svg viewBox="0 0 24 24" className="ml-1 size-6" fill="currentColor"><path d="M8 5v14l11-7z" /></svg>
            </span>
          </button>
        )}
      </div>
      <figcaption className="mt-1.5 text-xs text-slate-500">
        <span className="font-medium text-slate-700">{video.channel}</span> · {video.title} ·{' '}
        <a className="hover:text-brand-700" href={`https://www.youtube.com/watch?v=${video.id}`} target="_blank" rel="noreferrer">YouTube ↗</a>
      </figcaption>
    </figure>
  )
}
