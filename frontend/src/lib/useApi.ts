import { useCallback, useEffect, useState } from 'react'
import { api } from './api'

/** GET `path` on mount (and when it changes). `reload()` refetches. `path = null` skips the request. */
export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [loading, setLoading] = useState(path !== null)

  const load = useCallback(async () => {
    if (path === null) return
    setLoading(true)
    try {
      setData(await api.get<T>(path))
      setError(null)
    } catch (e) {
      setError(e as Error)
    } finally {
      setLoading(false)
    }
  }, [path])

  useEffect(() => { load() }, [load])
  return { data, error, loading, reload: load, setData }
}
