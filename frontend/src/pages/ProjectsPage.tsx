import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FolderOpen, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Button, Card, EmptyState, ErrorText, Field, Input, Modal, PageHeader, Select, Textarea } from '../components/ui'
import { api } from '../lib/api'
import { useSystemInfo } from '../lib/queries'
import type { Project } from '../lib/types'

export function ProjectsPage() {
  const qc = useQueryClient()
  const nav = useNavigate()
  const { data: projects = [], isLoading } = useQuery({ queryKey: ['projects'], queryFn: () => api.get<Project[]>('/projects') })
  const { data: system } = useSystemInfo()
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ name: '', premise: '', style_preset: '' })

  const create = useMutation({
    mutationFn: () => api.post<Project>('/projects', form),
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: ['projects'] })
      setOpen(false)
      nav(`/p/${p.id}`)
    },
  })
  const remove = useMutation({
    mutationFn: (id: number) => api.del(`/projects/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['projects'] }),
  })

  return (
    <div className="mx-auto max-w-5xl p-8">
      <PageHeader
        title="Projects"
        subtitle="Each project is one visual novel: its cast, locations and scenes."
        actions={
          <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setOpen(true)}>
            New project
          </Button>
        }
      />
      {!isLoading && projects.length === 0 ? (
        <EmptyState icon={<FolderOpen className="size-10" />} title="No projects yet">
          Create a project, add characters and a location, then let the writer draft your first scene.
        </EmptyState>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((p) => (
            <Card key={p.id} className="group relative p-5 transition hover:border-accent/50">
              <Link to={`/p/${p.id}`} className="absolute inset-0" />
              <h3 className="font-semibold text-zinc-100">{p.name}</h3>
              <p className="mt-2 line-clamp-3 text-sm text-zinc-500">{p.premise || 'No premise yet.'}</p>
              <div className="mt-4 flex items-center justify-between text-xs text-zinc-600">
                <span>{new Date(p.created_at).toLocaleDateString()}</span>
                <button
                  className="relative z-10 rounded p-1 opacity-0 transition group-hover:opacity-100 hover:bg-red-500/10 hover:text-red-300"
                  onClick={() => confirm(`Delete "${p.name}" and all its content?`) && remove.mutate(p.id)}
                >
                  <Trash2 className="size-4" />
                </button>
              </div>
            </Card>
          ))}
        </div>
      )}

      <Modal open={open} onClose={() => setOpen(false)} title="New project">
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            create.mutate()
          }}
        >
          <Field label="Title">
            <Input autoFocus value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Moonlit Library" />
          </Field>
          <Field label="Premise" hint="The writer model uses this as the backbone of every scene.">
            <Textarea
              rows={4}
              value={form.premise}
              onChange={(e) => setForm({ ...form, premise: e.target.value })}
              placeholder="A shy librarian discovers her new coworker is a runaway witch..."
            />
          </Field>
          <Field label="Art style" hint="Leave on default to use the style from Settings.">
            <Select value={form.style_preset} onChange={(e) => setForm({ ...form, style_preset: e.target.value })}>
              <option value="">Default (from Settings)</option>
              {Object.entries(system?.style_presets ?? {}).map(([k, label]) => (
                <option key={k} value={k}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
          <ErrorText error={create.error} />
          <div className="flex justify-end">
            <Button type="submit" variant="primary" loading={create.isPending} disabled={!form.name.trim()}>
              Create
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
