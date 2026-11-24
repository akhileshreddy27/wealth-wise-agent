import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import Markdown from 'react-markdown'
import { Link } from 'react-router-dom'
import remarkGfm from 'remark-gfm'
import { Button, cx, inputClass, PageHeader, Spinner } from '../components/ui'
import { api } from '../lib/api'
import type { ChatMessage, ChatReply } from '../lib/api'

type Turn = ChatMessage & { meta?: Omit<ChatReply, 'reply'> }

const SUGGESTIONS = [
  'Explain my plan in simple words',
  'What is the NAV of Parag Parikh Flexi Cap Fund today?',
  'How much SIP do I need for ₹20 lakh in 8 years?',
  'Where am I overspending?',
  'Is HDFCBANK a good pick for me?',
  'FD or debt fund for money I need in 2 years?',
]

const TOOL_LABEL: Record<string, string> = {
  search_knowledge: '📚 Searched lessons', get_stock_quote: '📈 Live stock price', get_fund_nav: '📊 Live fund NAV',
  get_stock_score: '🧮 Stock score', plan_goal: '🎯 Goal calculator', get_my_plan: '🗂️ Your plan', get_my_spending: '💳 Your spending',
}
const STORAGE_KEY = 'wealthwise.chat'
const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')

export default function Assistant({ aiEnabled }: { aiEnabled: boolean }) {
  const [turns, setTurns] = useState<Turn[]>(() => JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? '[]'))
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(turns))
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [turns, busy])

  async function send(text: string) {
    if (!text.trim() || busy) return
    const history: Turn[] = [...turns, { role: 'user', content: text.trim() }]
    setTurns(history)
    setInput('')
    setBusy(true)
    setError(null)
    try {
      const r = await api.post<ChatReply>('/chat', { messages: history.slice(-20).map(({ role, content }) => ({ role, content })) })
      setTurns([...history, { role: 'assistant', content: r.reply, meta: { sources: r.sources, tools_used: r.tools_used, mode: r.mode } }])
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const onSubmit = (e: FormEvent) => { e.preventDefault(); send(input) }

  return (
    <div className="flex h-[calc(100vh-7rem)] flex-col">
      <PageHeader
        title="Assistant"
        subtitle={aiEnabled
          ? 'Gemini agent with tools: your plan and spending, live NSE prices and AMFI NAVs, and the Learn lessons (cited).'
          : 'AI is off: answers come straight from the lessons. Add GEMINI_API_KEY to backend/.env for full answers.'}
        actions={turns.length > 0 && <Button variant="ghost" onClick={() => setTurns([])}>New chat</Button>}
      />

      <div className="flex-1 space-y-5 overflow-y-auto rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        {turns.length === 0 && (
          <div className="py-8 text-center">
            <p className="text-slate-500">Ask anything about your money. Try:</p>
            <div className="mx-auto mt-4 flex max-w-2xl flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((s) => (
                <button key={s} onClick={() => send(s)} className="rounded-full border border-slate-200 px-3 py-1.5 text-sm text-slate-700 hover:border-brand-600 hover:text-brand-800">{s}</button>
              ))}
            </div>
          </div>
        )}

        {turns.map((t, i) => (
          <div key={i} className={cx('flex', t.role === 'user' && 'justify-end')}>
            <div className={cx('max-w-[85%] rounded-2xl px-4 py-3', t.role === 'user' ? 'bg-brand-700 text-white' : 'bg-slate-50')}>
              {t.role === 'user' ? <p className="whitespace-pre-wrap text-sm">{t.content}</p> : (
                <>
                  <div className="prose prose-sm prose-slate max-w-none"><Markdown remarkPlugins={[remarkGfm]}>{t.content}</Markdown></div>
                  {t.meta && t.meta.tools_used.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {[...new Set(t.meta.tools_used.map((u) => u.name))].map((name) => (
                        <span key={name} className="rounded-full bg-white px-2 py-0.5 text-xs text-slate-500 ring-1 ring-slate-200">{TOOL_LABEL[name] ?? name}</span>
                      ))}
                    </div>
                  )}
                  {t.meta && t.meta.sources.length > 0 && (
                    <div className="mt-3 border-t border-slate-200 pt-2 text-xs text-slate-500">
                      Sources:{' '}
                      {t.meta.sources.map((s, j) => (
                        <span key={s.id}>{j > 0 && ' · '}
                          <Link className="text-brand-700 hover:underline" to={`/learn/${s.module_id}#${slug(s.section)}`}>[{s.n}] {s.module_title}: {s.section}</Link>
                        </span>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        ))}
        {busy && <div className="flex items-center gap-2 text-sm text-slate-500"><Spinner small /> Thinking…</div>}
        {error && <div className="text-sm text-rose-600">⚠️ {error}</div>}
        <div ref={endRef} />
      </div>

      <form onSubmit={onSubmit} className="mt-3 flex gap-2">
        <input className={inputClass} placeholder="Ask about SIPs, your plan, a stock, your spending…" value={input}
          onChange={(e) => setInput(e.target.value)} disabled={busy} />
        <Button type="submit" busy={busy} disabled={!input.trim()}>Send</Button>
      </form>
    </div>
  )
}
