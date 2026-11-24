import { lazy } from 'react'
import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import type { Health } from './lib/api'
import { useApi } from './lib/useApi'

// Each page is its own chunk, so charts and markdown only load where they're used.
const Assistant = lazy(() => import('./pages/Assistant'))
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Expenses = lazy(() => import('./pages/Expenses'))
const Learn = lazy(() => import('./pages/Learn'))
const LearnModule = lazy(() => import('./pages/LearnModule'))
const PlanPage = lazy(() => import('./pages/Plan'))
const ProfilePage = lazy(() => import('./pages/Profile'))

export default function App() {
  const health = useApi<Health>('/health')
  return (
    <Routes>
      <Route element={<Layout health={health.data} />}>
        <Route index element={<Dashboard health={health.data} />} />
        <Route path="plan" element={<PlanPage />} />
        <Route path="expenses" element={<Expenses />} />
        <Route path="learn" element={<Learn />} />
        <Route path="learn/:id" element={<LearnModule />} />
        <Route path="assistant" element={<Assistant aiEnabled={health.data?.ai_enabled ?? false} />} />
        <Route path="profile" element={<ProfilePage onSaved={health.reload} />} />
      </Route>
    </Routes>
  )
}
