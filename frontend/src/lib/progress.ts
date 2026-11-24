// Quiz progress is saved in the browser (localStorage): lesson id -> best score as a fraction.
const KEY = 'wealthwise.quiz'

export function loadProgress(): Record<string, number> {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? '{}')
  } catch {
    return {}
  }
}

export function saveScore(moduleId: string, score: number) {
  const all = loadProgress()
  all[moduleId] = Math.max(all[moduleId] ?? 0, score)
  localStorage.setItem(KEY, JSON.stringify(all))
}
