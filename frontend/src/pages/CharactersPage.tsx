import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { CheckCircle2, Dumbbell, ImagePlus, Plus, Save, Sparkles, Tags, Trash2, Upload, Users, Wand2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Lightbox } from '../components/Lightbox'
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorText,
  Field,
  Input,
  Modal,
  PageHeader,
  Progress,
  Select,
  Textarea,
} from '../components/ui'
import { api, fileUrl } from '../lib/api'
import { useJob } from '../lib/jobs'
import { useProject } from '../lib/queries'
import type { Character, ImageAsset, RefImage, TrainingRun } from '../lib/types'

type Tab = 'profile' | 'training' | 'test'

export function CharactersPage() {
  const pid = Number(useParams().projectId)
  const qc = useQueryClient()
  const { data: project } = useProject(pid)
  const [selected, setSelected] = useState<number | null>(null)
  const [newOpen, setNewOpen] = useState(false)
  const [newName, setNewName] = useState('')

  const characters = project?.characters ?? []
  const current = characters.find((c) => c.id === selected) ?? characters[0]

  const create = useMutation({
    mutationFn: () => api.post<Character>(`/projects/${pid}/characters`, { name: newName }),
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: ['project', pid] })
      setSelected(c.id)
      setNewOpen(false)
      setNewName('')
    },
  })

  return (
    <div className="mx-auto max-w-6xl p-8">
      <PageHeader
        title="Characters"
        subtitle="Personality drives the dialogue; reference images and a trained LoRA keep them looking the same in every image."
        actions={
          <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setNewOpen(true)}>
            New character
          </Button>
        }
      />
      {characters.length === 0 ? (
        <EmptyState icon={<Users className="size-10" />} title="No characters yet">
          Add your cast. You can let the writer model flesh out a sheet from a one-line brief.
        </EmptyState>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
          <div className="space-y-1">
            {characters.map((c) => (
              <button
                key={c.id}
                onClick={() => setSelected(c.id)}
                className={clsx(
                  'flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm transition',
                  current?.id === c.id ? 'bg-ink-800 text-zinc-100' : 'text-zinc-400 hover:bg-ink-900',
                )}
              >
                {c.ref_images[0] ? (
                  <img src={fileUrl(c.ref_images[0].file)} className="size-8 rounded-full object-cover" />
                ) : (
                  <span className="flex size-8 items-center justify-center rounded-full text-xs font-bold text-black" style={{ background: c.color }}>
                    {c.name[0]}
                  </span>
                )}
                <span className="flex-1 truncate">{c.name}</span>
                {c.lora_path && <span className="text-[10px] font-semibold text-emerald-400">LoRA</span>}
              </button>
            ))}
          </div>
          {current && <CharacterEditor key={current.id} character={current} projectId={pid} />}
        </div>
      )}

      <Modal open={newOpen} onClose={() => setNewOpen(false)} title="New character">
        <form
          onSubmit={(e) => {
            e.preventDefault()
            create.mutate()
          }}
          className="space-y-4"
        >
          <Field label="Name">
            <Input autoFocus value={newName} onChange={(e) => setNewName(e.target.value)} />
          </Field>
          <ErrorText error={create.error} />
          <div className="flex justify-end">
            <Button type="submit" variant="primary" disabled={!newName.trim()} loading={create.isPending}>
              Create
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  )
}

function CharacterEditor({ character, projectId }: { character: Character; projectId: number }) {
  const [tab, setTab] = useState<Tab>('profile')
  return (
    <Card className="overflow-hidden">
      <div className="flex border-b border-ink-700 px-2">
        {(
          [
            ['profile', 'Profile'],
            ['training', `References & LoRA (${character.ref_images.length})`],
            ['test', 'Test render'],
          ] as [Tab, string][]
        ).map(([t, label]) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={clsx(
              'border-b-2 px-4 py-3 text-sm transition',
              tab === t ? 'border-accent text-zinc-100' : 'border-transparent text-zinc-500 hover:text-zinc-300',
            )}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="p-5">
        {tab === 'profile' && <ProfileTab character={character} projectId={projectId} />}
        {tab === 'training' && <TrainingTab character={character} projectId={projectId} />}
        {tab === 'test' && <TestTab character={character} />}
      </div>
    </Card>
  )
}

const PROFILE_FIELDS: [keyof Character, string, number, string][] = [
  ['description', 'Role in the story', 3, ''],
  ['personality', 'Personality', 3, 'Traits, quirks, fears, desires'],
  ['speech_style', 'Speech style', 2, 'Vocabulary, verbal tics, formality'],
  ['relationships', 'Relationships', 2, ''],
  ['appearance', 'Appearance', 2, 'Natural-language description'],
  ['appearance_tags', 'Appearance tags (for images)', 2, '1girl, long silver hair, red eyes, school uniform'],
]

function ProfileTab({ character, projectId }: { character: Character; projectId: number }) {
  const qc = useQueryClient()
  const [form, setForm] = useState(character)
  const [brief, setBrief] = useState('')
  useEffect(() => setForm(character), [character])

  const save = useMutation({
    mutationFn: () => api.patch(`/characters/${character.id}`, form),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['project', projectId] }),
  })
  const expand = useMutation({
    mutationFn: () => api.post<Partial<Character>>(`/projects/${projectId}/characters/expand`, { name: form.name, brief }),
    onSuccess: (data) => setForm((f) => ({ ...f, ...Object.fromEntries(Object.entries(data).filter(([, v]) => v)) })),
  })
  const remove = useMutation({
    mutationFn: () => api.del(`/characters/${character.id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['project', projectId] }),
  })

  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-[1fr_120px]">
        <Field label="Name">
          <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </Field>
        <Field label="Text color">
          <Input type="color" className="p-1" value={form.color} onChange={(e) => setForm({ ...form, color: e.target.value })} />
        </Field>
      </div>

      <div className="rounded-lg border border-accent/30 bg-accent/5 p-3">
        <div className="flex gap-2">
          <Input value={brief} onChange={(e) => setBrief(e.target.value)} placeholder="One-line brief, e.g. 'sarcastic runaway witch who secretly loves books'" />
          <Button variant="primary" icon={<Sparkles className="size-4" />} loading={expand.isPending} onClick={() => expand.mutate()}>
            Flesh out
          </Button>
        </div>
        <ErrorText error={expand.error} />
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {PROFILE_FIELDS.map(([key, label, rows, placeholder]) => (
          <Field key={key} label={label}>
            <Textarea
              rows={rows}
              placeholder={placeholder}
              value={String(form[key] ?? '')}
              onChange={(e) => setForm({ ...form, [key]: e.target.value })}
            />
          </Field>
        ))}
      </div>
      <ErrorText error={save.error} />
      <div className="flex justify-between">
        <Button variant="danger" icon={<Trash2 className="size-4" />} onClick={() => confirm(`Delete ${character.name}?`) && remove.mutate()}>
          Delete
        </Button>
        <Button variant="primary" icon={<Save className="size-4" />} loading={save.isPending} onClick={() => save.mutate()}>
          Save profile
        </Button>
      </div>
    </div>
  )
}

function TrainingTab({ character, projectId }: { character: Character; projectId: number }) {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const loraRef = useRef<HTMLInputElement>(null)
  const [refs, setRefs] = useState(character.ref_images)
  const [trigger, setTrigger] = useState(character.trigger_word)
  const [weight, setWeight] = useState(character.lora_weight)
  const [preset, setPreset] = useState('fast')
  const [steps, setSteps] = useState('')
  const [captionJob, setCaptionJob] = useState<number | null>(null)
  const [lightbox, setLightbox] = useState<string | null>(null)
  useEffect(() => {
    setRefs(character.ref_images)
    setTrigger(character.trigger_word)
    setWeight(character.lora_weight)
  }, [character])

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['project', projectId] })
    qc.invalidateQueries({ queryKey: ['runs', character.id] })
  }
  const { data: presets = {} } = useQuery({
    queryKey: ['training-presets'],
    queryFn: () => api.get<Record<string, { label: string; steps: number }>>('/training/presets'),
  })
  const { data: runs = [] } = useQuery({
    queryKey: ['runs', character.id],
    queryFn: () => api.get<TrainingRun[]>(`/characters/${character.id}/training-runs`),
  })
  const captionStatus = useJob(captionJob)

  const upload = useMutation({
    mutationFn: (files: FileList) => {
      const fd = new FormData()
      Array.from(files).forEach((f) => fd.append('files', f))
      return api.post(`/characters/${character.id}/refs`, fd)
    },
    onSuccess: refresh,
  })
  const saveRefs = useMutation({
    mutationFn: async (list: RefImage[]) => {
      await api.patch(`/characters/${character.id}`, { trigger_word: trigger, lora_weight: weight })
      return api.patch(`/characters/${character.id}/refs`, list)
    },
    onSuccess: refresh,
  })
  const caption = useMutation({
    mutationFn: (overwrite: boolean) => api.post<{ job_id: number }>(`/characters/${character.id}/caption`, { overwrite }),
    onSuccess: (r) => setCaptionJob(r.job_id),
  })
  const train = useMutation({
    mutationFn: async () => {
      await saveRefs.mutateAsync(refs)
      return api.post(`/characters/${character.id}/train`, { preset, steps: steps ? Number(steps) : undefined })
    },
    onSuccess: refresh,
  })
  const importLora = useMutation({
    mutationFn: (file: File) => {
      const fd = new FormData()
      fd.append('file', file)
      return api.post(`/characters/${character.id}/lora`, fd)
    },
    onSuccess: refresh,
  })
  const clearLora = useMutation({ mutationFn: () => api.patch(`/characters/${character.id}`, { lora_path: '' }), onSuccess: refresh })

  const dirty = JSON.stringify(refs) !== JSON.stringify(character.ref_images) || trigger !== character.trigger_word || weight !== character.lora_weight

  return (
    <div className="space-y-6">
      <section className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="text-sm font-semibold text-zinc-200">Reference images</h3>
            <p className="text-xs text-zinc-500">5-20 clean images of the character (varied poses and framing). Used to train the LoRA and as IP-Adapter references until a LoRA exists.</p>
          </div>
          <div className="flex gap-2">
            <input ref={fileRef} type="file" multiple accept="image/*" hidden onChange={(e) => e.target.files && upload.mutate(e.target.files)} />
            <Button icon={<Upload className="size-4" />} loading={upload.isPending} onClick={() => fileRef.current?.click()}>
              Upload
            </Button>
            <Button icon={<Tags className="size-4" />} loading={caption.isPending || captionStatus?.status === 'running'} disabled={!refs.length} onClick={() => caption.mutate(false)}>
              Auto-caption
            </Button>
          </div>
        </div>
        {captionStatus && captionStatus.status !== 'done' && (
          <div className="space-y-1 text-xs text-zinc-500">
            <Progress value={captionStatus.progress} />
            <span>{captionStatus.error || captionStatus.message}</span>
          </div>
        )}
        {refs.length === 0 ? (
          <button
            onClick={() => fileRef.current?.click()}
            className="flex w-full flex-col items-center gap-2 rounded-xl border border-dashed border-ink-600 py-10 text-sm text-zinc-500 hover:border-accent/60"
          >
            <ImagePlus className="size-8" />
            Drop in reference images
          </button>
        ) : (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4">
            {refs.map((r, i) => (
              <div key={r.file} className="group overflow-hidden rounded-lg border border-ink-700 bg-ink-850">
                <div className="relative">
                  <img src={fileUrl(r.file)} className="aspect-square w-full cursor-zoom-in object-cover" onClick={() => setLightbox(r.file)} />
                  <button
                    className="absolute top-1.5 right-1.5 rounded-md bg-black/60 p-1 text-zinc-300 opacity-0 transition group-hover:opacity-100 hover:text-red-300"
                    onClick={() => setRefs(refs.filter((_, j) => j !== i))}
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </div>
                <textarea
                  className="h-16 w-full resize-none bg-transparent p-2 text-[11px] text-zinc-400 focus:outline-none"
                  placeholder="caption (tags)"
                  value={r.caption}
                  onChange={(e) => setRefs(refs.map((x, j) => (j === i ? { ...x, caption: e.target.value } : x)))}
                />
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        <Field label="Trigger word" hint="Unique token the LoRA learns for this character.">
          <Input value={trigger} onChange={(e) => setTrigger(e.target.value)} />
        </Field>
        <Field label={`LoRA weight: ${weight.toFixed(2)}`}>
          <input type="range" min={0} max={1.5} step={0.05} value={weight} onChange={(e) => setWeight(Number(e.target.value))} className="mt-2 w-full accent-violet-500" />
        </Field>
        <div className="flex items-end">
          <Button className="w-full" icon={<Save className="size-4" />} disabled={!dirty} loading={saveRefs.isPending} onClick={() => saveRefs.mutate(refs)}>
            Save changes
          </Button>
        </div>
      </section>

      <section className="space-y-3 rounded-xl border border-ink-700 bg-ink-850 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="text-sm font-semibold text-zinc-200">Character LoRA</h3>
            <p className="text-xs text-zinc-500">
              {character.lora_path ? (
                <span className="text-emerald-400">Active: {character.lora_path.split('/').pop()}</span>
              ) : (
                'No LoRA yet - images use reference images (IP-Adapter) and tags.'
              )}
            </p>
          </div>
          <div className="flex gap-2">
            <input ref={loraRef} type="file" accept=".safetensors" hidden onChange={(e) => e.target.files?.[0] && importLora.mutate(e.target.files[0])} />
            <Button size="sm" variant="ghost" loading={importLora.isPending} onClick={() => loraRef.current?.click()}>
              Import .safetensors
            </Button>
            {character.lora_path && (
              <Button size="sm" variant="ghost" onClick={() => clearLora.mutate()}>
                Detach
              </Button>
            )}
          </div>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Preset" className="min-w-56 flex-1">
            <Select value={preset} onChange={(e) => setPreset(e.target.value)}>
              {Object.entries(presets).map(([k, p]) => (
                <option key={k} value={k}>
                  {p.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Steps (optional)" className="w-36">
            <Input type="number" placeholder={String(presets[preset]?.steps ?? '')} value={steps} onChange={(e) => setSteps(e.target.value)} />
          </Field>
          <Button variant="primary" icon={<Dumbbell className="size-4" />} loading={train.isPending} disabled={refs.length < 3} onClick={() => train.mutate()}>
            Train LoRA
          </Button>
        </div>
        <ErrorText error={train.error || upload.error || importLora.error || caption.error} />
        <p className="text-xs text-zinc-500">
          Training uses the default checkpoint from Settings. On Apple Silicon expect tens of minutes to hours; on a modern NVIDIA GPU, a few minutes to about half an hour.
        </p>
        <div className="space-y-3">
          {runs.map((run) => (
            <TrainingRunCard key={run.id} run={run} character={character} onChange={refresh} onZoom={setLightbox} />
          ))}
        </div>
      </section>
      <Lightbox path={lightbox} onClose={() => setLightbox(null)} />
    </div>
  )
}

function TrainingRunCard({
  run,
  character,
  onChange,
  onZoom,
}: {
  run: TrainingRun
  character: Character
  onChange: () => void
  onZoom: (p: string) => void
}) {
  const job = useJob(run.job_id)
  const use = useMutation({ mutationFn: (step: number) => api.post(`/training-runs/${run.id}/use`, { step }), onSuccess: onChange })
  const remove = useMutation({ mutationFn: () => api.del(`/training-runs/${run.id}`), onSuccess: onChange })
  const cancel = useMutation({ mutationFn: () => api.post(`/jobs/${run.job_id}/cancel`) })
  const running = run.status === 'running' || run.status === 'queued'
  return (
    <div className="rounded-lg border border-ink-700 bg-ink-900 p-3">
      <div className="flex items-center justify-between gap-2 text-sm">
        <div className="flex items-center gap-2">
          <span className="font-medium text-zinc-200">Run #{run.id}</span>
          <Badge status={job?.status === 'failed' ? 'failed' : run.status} />
          <span className="text-xs text-zinc-500">
            {run.preset} - {run.params.steps} steps - rank {run.params.rank}
          </span>
        </div>
        {running ? (
          <Button size="sm" variant="danger" onClick={() => cancel.mutate()}>
            Cancel
          </Button>
        ) : (
          <Button size="sm" variant="ghost" icon={<Trash2 className="size-3.5" />} onClick={() => confirm('Delete this run and its files?') && remove.mutate()} />
        )}
      </div>
      {job && (job.status === 'running' || job.status === 'queued') && (
        <div className="mt-2 space-y-1">
          <Progress value={job.progress} />
          <p className="text-xs text-zinc-500">{job.message}</p>
        </div>
      )}
      {job?.status === 'failed' && <p className="mt-2 text-xs text-red-300">{job.error}</p>}
      {run.checkpoints.length > 0 && (
        <div className="mt-3 space-y-2">
          {run.checkpoints.map((cp) => {
            const active = character.lora_path === cp.path
            return (
              <div key={cp.step} className={clsx('flex items-center gap-3 rounded-md p-2', active ? 'bg-emerald-500/10' : 'bg-ink-850')}>
                <span className="w-20 text-xs text-zinc-400">step {cp.step}</span>
                <div className="flex flex-1 gap-2 overflow-x-auto">
                  {cp.samples.map((s) => (
                    <img key={s} src={fileUrl(s)} className="size-16 cursor-zoom-in rounded object-cover" onClick={() => onZoom(s)} />
                  ))}
                </div>
                {active ? (
                  <span className="flex items-center gap-1 text-xs text-emerald-400">
                    <CheckCircle2 className="size-4" /> in use
                  </span>
                ) : (
                  <Button size="sm" onClick={() => use.mutate(cp.step)}>
                    Use this
                  </Button>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function TestTab({ character }: { character: Character }) {
  const [extra, setExtra] = useState('')
  const [jobId, setJobId] = useState<number | null>(null)
  const [lightbox, setLightbox] = useState<ImageAsset | null>(null)
  const job = useJob(jobId)
  const { data: images = [] } = useQuery({
    queryKey: ['character-images', character.id],
    queryFn: () => api.get<ImageAsset[]>(`/characters/${character.id}/images`),
  })
  const qc = useQueryClient()
  const gen = useMutation({
    mutationFn: () => api.post<{ job_id: number }>(`/characters/${character.id}/test-image`, { extra, count: 2 }),
    onSuccess: (r) => setJobId(r.job_id),
  })
  const del = useMutation({
    mutationFn: (id: number) => api.del(`/images/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['character-images', character.id] }),
  })
  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <Input value={extra} onChange={(e) => setExtra(e.target.value)} placeholder="upper body, smiling, cafe background (optional)" />
        <Button variant="primary" icon={<Wand2 className="size-4" />} loading={gen.isPending} onClick={() => gen.mutate()}>
          Render
        </Button>
      </div>
      <ErrorText error={gen.error} />
      {job && job.status !== 'done' && (
        <div className="space-y-1 text-xs text-zinc-500">
          <Progress value={job.progress} />
          <span className={job.status === 'failed' ? 'text-red-300' : ''}>{job.error || job.message}</span>
        </div>
      )}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4">
        {images.map((img) => (
          <div key={img.id} className="group relative overflow-hidden rounded-lg border border-ink-700">
            <img src={fileUrl(img.path)} className="w-full cursor-zoom-in" onClick={() => setLightbox(img)} />
            <button
              className="absolute top-1.5 right-1.5 rounded-md bg-black/60 p-1 text-zinc-300 opacity-0 group-hover:opacity-100 hover:text-red-300"
              onClick={() => del.mutate(img.id)}
            >
              <Trash2 className="size-3.5" />
            </button>
          </div>
        ))}
      </div>
      <Lightbox path={lightbox?.path ?? null} caption={lightbox ? `seed ${lightbox.seed} - ${lightbox.prompt}` : ''} onClose={() => setLightbox(null)} />
    </div>
  )
}
