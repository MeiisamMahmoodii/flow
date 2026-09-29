import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Clapperboard, Download, FileJson, MapPin, Plus, Save, Trash2, Users } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { SceneForm, type SceneFormValue } from '../components/SceneForm'
import { Badge, Button, Card, EmptyState, ErrorText, Field, Modal, PageHeader, Select, Textarea } from '../components/ui'
import { api } from '../lib/api'
import { useProject, useSystemInfo } from '../lib/queries'
import type { Scene } from '../lib/types'

const emptyScene: SceneFormValue = { title: '', location_id: null, cast_ids: [], goal: '', outline: '' }

export function ProjectPage() {
  const pid = Number(useParams().projectId)
  const qc = useQueryClient()
  const { data: project } = useProject(pid)
  const { data: system } = useSystemInfo()
  const [open, setOpen] = useState(false)
  const [scene, setScene] = useState<SceneFormValue>(emptyScene)
  const [meta, setMeta] = useState({ premise: '', style_preset: '' })

  useEffect(() => {
    if (project) setMeta({ premise: project.premise, style_preset: project.style_preset })
  }, [project])

  const refresh = () => qc.invalidateQueries({ queryKey: ['project', pid] })
  const createScene = useMutation({
    mutationFn: () => api.post<Scene>(`/projects/${pid}/scenes`, scene),
    onSuccess: () => {
      refresh()
      setOpen(false)
      setScene(emptyScene)
    },
  })
  const saveMeta = useMutation({ mutationFn: () => api.patch(`/projects/${pid}`, meta), onSuccess: refresh })
  const removeScene = useMutation({ mutationFn: (id: number) => api.del(`/scenes/${id}`), onSuccess: refresh })

  if (!project) return null
  const locName = (id: number | null) => project.locations.find((l) => l.id === id)?.name
  const charName = (id: number) => project.characters.find((c) => c.id === id)?.name

  return (
    <div className="mx-auto max-w-5xl p-8">
      <PageHeader
        title={project.name}
        subtitle={`${project.characters.length} characters, ${project.locations.length} locations, ${project.scenes.length} scenes`}
        actions={
          <>
            <a href={`/api/projects/${pid}/export/json`}>
              <Button variant="ghost" icon={<FileJson className="size-4" />}>
                JSON
              </Button>
            </a>
            <a href={`/api/projects/${pid}/export/renpy`}>
              <Button icon={<Download className="size-4" />}>Export Ren'Py</Button>
            </a>
            <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setOpen(true)}>
              New scene
            </Button>
          </>
        }
      />

      {(project.characters.length === 0 || project.locations.length === 0) && (
        <Card className="mb-6 flex flex-wrap items-center gap-4 border-accent/30 bg-accent/5 p-4 text-sm">
          <span className="text-zinc-300">Set up your cast and world first:</span>
          <Link to={`/p/${pid}/characters`}>
            <Button size="sm" icon={<Users className="size-3.5" />}>
              Characters ({project.characters.length})
            </Button>
          </Link>
          <Link to={`/p/${pid}/locations`}>
            <Button size="sm" icon={<MapPin className="size-3.5" />}>
              Locations ({project.locations.length})
            </Button>
          </Link>
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <div className="space-y-3">
          {project.scenes.length === 0 ? (
            <EmptyState icon={<Clapperboard className="size-10" />} title="No scenes yet">
              A scene has a location, a cast and a goal. The writer drafts it block by block; you approve each block and
              an illustration is generated for it.
            </EmptyState>
          ) : (
            project.scenes.map((s, i) => (
              <Card key={s.id} className="group relative flex items-start gap-4 p-4 transition hover:border-accent/50">
                <Link to={`/p/${pid}/scenes/${s.id}`} className="absolute inset-0" />
                <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-ink-800 text-sm font-semibold text-zinc-400">
                  {i + 1}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <h3 className="font-medium text-zinc-100">{s.title}</h3>
                    <Badge status={s.status} />
                  </div>
                  <p className="mt-1 text-xs text-zinc-500">
                    {locName(s.location_id) ?? 'No location'} - {s.cast_ids.map(charName).filter(Boolean).join(', ') || 'Whole cast'}
                  </p>
                  {(s.summary || s.goal) && <p className="mt-2 line-clamp-2 text-sm text-zinc-400">{s.summary || `Goal: ${s.goal}`}</p>}
                </div>
                <button
                  className="relative z-10 rounded p-1 text-zinc-600 opacity-0 transition group-hover:opacity-100 hover:bg-red-500/10 hover:text-red-300"
                  onClick={() => confirm(`Delete scene "${s.title}"?`) && removeScene.mutate(s.id)}
                >
                  <Trash2 className="size-4" />
                </button>
              </Card>
            ))
          )}
        </div>

        <Card className="h-fit space-y-4 p-4">
          <h3 className="text-sm font-semibold text-zinc-200">Story bible</h3>
          <Field label="Premise">
            <Textarea rows={7} value={meta.premise} onChange={(e) => setMeta({ ...meta, premise: e.target.value })} />
          </Field>
          <Field label="Art style">
            <Select value={meta.style_preset} onChange={(e) => setMeta({ ...meta, style_preset: e.target.value })}>
              <option value="">Default (from Settings)</option>
              {Object.entries(system?.style_presets ?? {}).map(([k, label]) => (
                <option key={k} value={k}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
          <Button className="w-full" icon={<Save className="size-4" />} loading={saveMeta.isPending} onClick={() => saveMeta.mutate()}>
            Save
          </Button>
        </Card>
      </div>

      <Modal open={open} onClose={() => setOpen(false)} title="New scene">
        <SceneForm value={scene} onChange={setScene} project={project} />
        <ErrorText error={createScene.error} />
        <div className="mt-4 flex justify-end">
          <Button variant="primary" loading={createScene.isPending} disabled={!scene.title.trim()} onClick={() => createScene.mutate()}>
            Create scene
          </Button>
        </div>
      </Modal>
    </div>
  )
}
