import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, ListChecks, Trash2, XCircle } from 'lucide-react'
import { useState } from 'react'
import { Badge, Button, Card, EmptyState, PageHeader, Progress } from '../components/ui'
import { api } from '../lib/api'
import { isActive, useJobs } from '../lib/jobs'
import type { Job } from '../lib/types'

export function JobsPage() {
  const qc = useQueryClient()
  const { data: jobs = [] } = useJobs()
  const clear = useMutation({ mutationFn: () => api.del('/jobs'), onSuccess: () => qc.invalidateQueries({ queryKey: ['jobs'] }) })
  return (
    <div className="mx-auto max-w-4xl p-8">
      <PageHeader
        title="Jobs"
        subtitle="Image generation and training share one GPU queue; they run one at a time."
        actions={
          <Button variant="ghost" icon={<Trash2 className="size-4" />} onClick={() => clear.mutate()}>
            Clear finished
          </Button>
        }
      />
      {jobs.length === 0 ? (
        <EmptyState icon={<ListChecks className="size-10" />} title="No jobs yet" />
      ) : (
        <div className="space-y-2">
          {jobs.map((j) => (
            <JobRow key={j.id} job={j} />
          ))}
        </div>
      )}
    </div>
  )
}

function JobRow({ job }: { job: Job }) {
  const [open, setOpen] = useState(false)
  const cancel = useMutation({ mutationFn: () => api.post(`/jobs/${job.id}/cancel`) })
  return (
    <Card className="p-3">
      <div className="flex items-center gap-3">
        <button onClick={() => setOpen(!open)} className="text-zinc-500 hover:text-zinc-200">
          {open ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
        </button>
        <span className="w-10 text-xs text-zinc-600">#{job.id}</span>
        <span className="w-36 text-sm font-medium text-zinc-200">{job.kind.replace('_', ' ')}</span>
        <Badge status={job.status} />
        <div className="min-w-0 flex-1">
          {isActive(job) ? <Progress value={job.progress} /> : null}
          <p className={`mt-1 truncate text-xs ${job.status === 'failed' ? 'text-red-300' : 'text-zinc-500'}`}>{job.error || job.message}</p>
        </div>
        <span className="text-xs text-zinc-600">{new Date(job.created_at + (job.created_at.endsWith('Z') ? '' : 'Z')).toLocaleTimeString()}</span>
        {isActive(job) && (
          <Button size="sm" variant="danger" icon={<XCircle className="size-3.5" />} onClick={() => cancel.mutate()}>
            Cancel
          </Button>
        )}
      </div>
      {open && (
        <pre className="mt-3 max-h-80 overflow-auto rounded-lg bg-ink-950 p-3 text-[11px] leading-relaxed whitespace-pre-wrap text-zinc-400">
          {job.logs || 'No logs.'}
        </pre>
      )}
    </Card>
  )
}
