import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { api } from './api'
import type { Job } from './types'

const FINISHED = new Set(['done', 'failed', 'cancelled'])

export function useJobs() {
  return useQuery({ queryKey: ['jobs'], queryFn: () => api.get<Job[]>('/jobs'), staleTime: 60_000 })
}

export function useJob(id: number | null | undefined) {
  const { data } = useJobs()
  return id ? data?.find((j) => j.id === id) : undefined
}

/** Keeps the jobs cache live from the backend WebSocket and refreshes data when jobs finish. */
export function useJobSocket() {
  const qc = useQueryClient()
  useEffect(() => {
    let ws: WebSocket | null = null
    let closed = false
    let retry: ReturnType<typeof setTimeout>

    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      ws = new WebSocket(`${proto}://${location.host}/ws`)
      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data)
        if (msg.type !== 'job') return
        const job: Job = msg.job
        let previous: Job | undefined
        qc.setQueryData<Job[]>(['jobs'], (old = []) => {
          previous = old.find((j) => j.id === job.id)
          const rest = old.filter((j) => j.id !== job.id)
          return [job, ...rest].sort((a, b) => b.id - a.id)
        })
        const statusChanged = previous?.status !== job.status
        if (statusChanged && (FINISHED.has(job.status) || job.status === 'running')) {
          qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== 'jobs' })
        }
      }
      ws.onclose = () => {
        if (!closed) retry = setTimeout(connect, 1500)
      }
    }
    connect()
    return () => {
      closed = true
      clearTimeout(retry)
      ws?.close()
    }
  }, [qc])
}

export const isActive = (j: Job) => j.status === 'queued' || j.status === 'running'
