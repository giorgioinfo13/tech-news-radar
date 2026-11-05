import { useCallback, useEffect, useState } from 'react'
import { allPages, errorMessage, request, type Page } from './api'

export function useQuery<T>(path: string, collectAll = false) {
  const [revision, setRevision] = useState(0)
  const [result, setResult] = useState<{
    key: string
    path: string
    data?: Page<T>
    error?: string
  }>()
  const key = `${path}:${revision}:${collectAll}`
  useEffect(() => {
    const controller = new AbortController()
    const pending = collectAll
      ? allPages<T>(path, controller.signal)
      : request<Page<T>>(path, { signal: controller.signal })
    pending.then(
      (data) => {
        if (!controller.signal.aborted) setResult({ key, path, data })
      },
      (error) => {
        if (!controller.signal.aborted)
          setResult((previous) => ({
            key,
            path,
            data: previous?.path === path ? previous.data : undefined,
            error: errorMessage(error),
          }))
      },
    )
    return () => controller.abort()
  }, [path, collectAll, key])
  const reload = useCallback(() => setRevision((value) => value + 1), [])
  return {
    data: result?.path === path ? result.data : undefined,
    error: result?.key === key ? result.error : undefined,
    loading: result?.key !== key,
    reload,
  }
}
