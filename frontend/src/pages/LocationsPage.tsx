import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { CheckCircle2, MapPin, Plus, Save, Trash2, Wand2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Lightbox } from '../components/Lightbox'
import { Button, Card, EmptyState, ErrorText, Field, Input, Modal, PageHeader, Progress, Textarea } from '../components/ui'
import { api, fileUrl } from '../lib/api'
import { useJob } from '../lib/jobs'
import { useProject } from '../lib/queries'
import type { ImageAsset, Location } from '../lib/types'

export function LocationsPage() {
  const pid = Number(useParams().projectId)
  const { data: project } = useProject(pid)
  const [editing, setEditing] = useState<Location | 'new' | null>(null)
  const locations = project?.locations ?? []

  return (
    <div className="mx-auto max-w-6xl p-8">
      <PageHeader
        title="Locations"
        subtitle="Where scenes take place. Their tags flow into every scene image; a background image is used in exports and play-through."
        actions={
          <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setEditing('new')}>
            New location
          </Button>
        }
      />
      {locations.length === 0 ? (
        <EmptyState icon={<MapPin className="size-10" />} title="No locations yet" />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {locations.map((l) => (
            <Card key={l.id} className="cursor-pointer overflow-hidden transition hover:border-accent/50">
              <div onClick={() => setEditing(l)}>
                {l.image_path ? (
                  <img src={fileUrl(l.image_path)} className="aspect-video w-full object-cover" />
                ) : (
                  <div className="checker flex aspect-video items-center justify-center text-zinc-600">
                    <MapPin className="size-8" />
                  </div>
                )}
                <div className="p-4">
                  <h3 className="font-medium text-zinc-100">{l.name}</h3>
                  <p className="mt-1 line-clamp-2 text-sm text-zinc-500">{l.description}</p>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
      {editing && (
        <LocationModal projectId={pid} location={editing === 'new' ? null : editing} onClose={() => setEditing(null)} />
      )}
    </div>
  )
}

function LocationModal({ projectId, location, onClose }: { projectId: number; location: Location | null; onClose: () => void }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({ name: '', description: '', tags: '' })
  const [jobId, setJobId] = useState<number | null>(null)
  const [zoom, setZoom] = useState<string | null>(null)
  const job = useJob(jobId)
  useEffect(() => {
    if (location) setForm({ name: location.name, description: location.description, tags: location.tags })
  }, [location])

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['project', projectId] })
    qc.invalidateQueries({ queryKey: ['location-images', location?.id] })
  }
  const { data: images = [] } = useQuery({
    queryKey: ['location-images', location?.id],
    queryFn: () => api.get<ImageAsset[]>(`/locations/${location!.id}/images`),
    enabled: !!location,
  })
  const save = useMutation({
    mutationFn: () => (location ? api.patch(`/locations/${location.id}`, form) : api.post(`/projects/${projectId}/locations`, form)),
    onSuccess: () => {
      refresh()
      if (!location) onClose()
    },
  })
  const remove = useMutation({
    mutationFn: () => api.del(`/locations/${location!.id}`),
    onSuccess: () => {
      refresh()
      onClose()
    },
  })
  const gen = useMutation({
    mutationFn: async () => {
      await api.patch(`/locations/${location!.id}`, form)
      return api.post<{ job_id: number }>(`/locations/${location!.id}/background`, { count: 2 })
    },
    onSuccess: (r) => setJobId(r.job_id),
  })
  const setBg = useMutation({
    mutationFn: (path: string) => api.patch(`/locations/${location!.id}`, { image_path: path }),
    onSuccess: refresh,
  })

  return (
    <Modal open onClose={onClose} title={location ? location.name : 'New location'} wide={!!location}>
      <div className={clsx('grid gap-6', location && 'md:grid-cols-[1fr_1.3fr]')}>
        <div className="space-y-4">
          <Field label="Name">
            <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </Field>
          <Field label="Description" hint="Given to the writer model for atmosphere.">
            <Textarea rows={4} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </Field>
          <Field label="Image tags" hint="Comma-separated tags added to every scene image here.">
            <Textarea rows={3} value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} placeholder="library, bookshelves, dusk, warm light" />
          </Field>
          <ErrorText error={save.error || gen.error} />
          <div className="flex justify-between">
            {location ? (
              <Button variant="danger" icon={<Trash2 className="size-4" />} onClick={() => confirm('Delete location?') && remove.mutate()}>
                Delete
              </Button>
            ) : (
              <span />
            )}
            <Button variant="primary" icon={<Save className="size-4" />} disabled={!form.name.trim()} loading={save.isPending} onClick={() => save.mutate()}>
              Save
            </Button>
          </div>
        </div>
        {location && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h4 className="text-sm font-semibold text-zinc-200">Background images</h4>
              <Button icon={<Wand2 className="size-4" />} loading={gen.isPending} onClick={() => gen.mutate()}>
                Generate
              </Button>
            </div>
            {job && job.status !== 'done' && (
              <div className="space-y-1 text-xs text-zinc-500">
                <Progress value={job.progress} />
                <span className={job.status === 'failed' ? 'text-red-300' : ''}>{job.error || job.message}</span>
              </div>
            )}
            <div className="grid grid-cols-2 gap-2">
              {images.map((img) => {
                const active = location.image_path === img.path
                return (
                  <div key={img.id} className={clsx('group relative overflow-hidden rounded-lg border-2', active ? 'border-emerald-500' : 'border-transparent')}>
                    <img src={fileUrl(img.path)} className="aspect-video w-full cursor-zoom-in object-cover" onClick={() => setZoom(img.path)} />
                    {active ? (
                      <CheckCircle2 className="absolute top-1.5 right-1.5 size-5 text-emerald-400" />
                    ) : (
                      <Button size="sm" className="absolute right-1.5 bottom-1.5 opacity-0 group-hover:opacity-100" onClick={() => setBg.mutate(img.path)}>
                        Use
                      </Button>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>
      <Lightbox path={zoom} onClose={() => setZoom(null)} />
    </Modal>
  )
}
