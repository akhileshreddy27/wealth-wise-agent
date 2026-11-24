import { Suspense } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import type { Health } from '../lib/api'
import { cx, Disclaimer, Loading } from './ui'

const NAV = [
  { to: '/', label: 'Dashboard', icon: 'M3 12l9-8 9 8M5 10v10h5v-6h4v6h5V10' },
  { to: '/plan', label: 'My Plan', icon: 'M4 19V9m6 10V5m6 14v-7m4 7H2' },
  { to: '/expenses', label: 'Expenses', icon: 'M3 7h18v12H3zM3 11h18M7 15h4' },
  { to: '/learn', label: 'Learn', icon: 'M12 6c-2-1.5-5-2-8-1.5V19c3-.5 6 0 8 1.5 2-1.5 5-2 8-1.5V4.5C17 4 14 4.5 12 6zm0 0v14.5' },
  { to: '/assistant', label: 'Assistant', icon: 'M4 5h16v11H8l-4 4zM8 9h8M8 12h5' },
  { to: '/profile', label: 'Profile', icon: 'M12 12a4 4 0 100-8 4 4 0 000 8zm-7 9a7 7 0 0114 0' },
]

function Icon({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 24 24" className="size-5 shrink-0" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
      <path d={d} />
    </svg>
  )
}

export default function Layout({ health }: { health: Health | null }) {
  return (
    <div className="min-h-screen md:flex">
      <aside className="border-b border-slate-200 bg-white md:sticky md:top-0 md:h-screen md:w-60 md:shrink-0 md:border-r md:border-b-0">
        <div className="flex items-center gap-2.5 px-5 py-4 md:py-6">
          <img src="/favicon.svg" alt="" className="size-8" />
          <div>
            <div className="font-semibold text-slate-900">Wealth Wise</div>
            <div className="text-xs text-slate-500">Personal finance assistant</div>
          </div>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-col md:pb-0">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) => cx('flex items-center gap-3 whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium transition',
                isActive ? 'bg-brand-50 text-brand-800' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900')}
            >
              <Icon d={item.icon} />
              {item.label}
            </NavLink>
          ))}
        </nav>
        {health && (
          <div className="hidden px-5 py-6 text-xs text-slate-500 md:absolute md:bottom-0 md:block">
            <div className="flex items-center gap-2">
              <span className={cx('size-2 rounded-full', health.ai_enabled ? 'bg-brand-500' : 'bg-slate-300')} />
              {health.ai_enabled ? 'Gemini AI on' : 'AI off (no API key)'}
            </div>
            <div className="mt-1">Lesson search: {health.knowledge_search}</div>
          </div>
        )}
      </aside>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 md:px-8 md:py-8">
        <Suspense fallback={<Loading />}><Outlet /></Suspense>
        <div className="mt-12"><Disclaimer /></div>
      </main>
    </div>
  )
}
