import { useMutation, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import {
  ArrowDown,
  ArrowUp,
  Brush,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Copy,
  Flag,
  ImagePlus,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  Sparkles,
  Trash2,
  Undo2,
  Wand2,
  ZoomIn,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Lightbox } from '../components/Lightbox'
import { MaskEditor } from '../components/MaskEditor'
import { SceneForm, type SceneFormValue } from '../components/SceneForm'
import { Badge, Button, Card, ErrorText, Input, Modal, Progress, Select, Spinner, Textarea } from '../components/ui'
import { VNPreview } from '../components/VNPreview'
import { api, fileUrl } from '../lib/api'
import { isActive, useJobs } from '../lib/jobs'
import { useProject, useScene } from '../lib/queries'
import type { Character, DialogueGroup, DialogueLine, ImageAsset, ProjectDetail, SceneDetail } from '../lib/types'

export function SceneEditorPage() {
  const pid = Number(useParams().projectId)
  const sid = Number(useParams().sceneId)
  const qc = useQueryClient()
  const { data: project } = useProject(pid)
  const { data: scene, isLoading } = useScene(sid)
  const [focus, setFocus] = useState<number | null>(null)
  const [editOpen, setEditOpen] = useState(false)

  const setScene = (s: SceneDetail) => {
    qc.setQueryData(['scene', sid], s)
    qc.invalidateQueries({ queryKey: ['project', pid] })
  }

  const complete = useMutation({ mutationFn: () => api.post<SceneDetail>(`/scenes/${sid}/complete`), onSuccess: setScene })
  const reopen = useMutation({ mutationFn: () => api.post<SceneDetail>(`/scenes/${sid}/reopen`), onSuccess: setScene })

  const groups = scene?.groups ?? []
  const focused = groups.find((g) => g.id === focus) ?? groups[groups.length - 1]

  if (isLoading || !scene || !project) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner className="size-6" />
      </div>
    )
  }
  const location = project.locations.find((l) => l.id === scene.location_id)
  const hasDraft = groups.some((g) => g.status === 'draft')

  return (
    <div className="flex min-h-full flex-col">
      <header className="sticky top-0 z-20 flex flex-wrap items-center gap-3 border-b border-ink-800 bg-ink-950/90 px-6 py-3 backdrop-blur">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h1 className="truncate text-lg font-semibold text-zinc-50">{scene.title}</h1>
            <Badge status={scene.status} />
            <button className="text-zinc-500 hover:text-zinc-200" onClick={() => setEditOpen(true)}>
              <Pencil className="size-3.5" />
            </button>
          </div>
          <p className="truncate text-xs text-zinc-500">
            {location?.name ?? 'No location'} - Goal: {scene.goal || 'open'}
          </p>
        </div>
        <Link to={`/p/${pid}/play`}>
          <Button size="sm" variant="ghost" icon={<Play className="size-3.5" />}>
            Play
          </Button>
        </Link>
        {scene.status === 'complete' ? (
          <Button size="sm" icon={<RotateCcw className="size-3.5" />} loading={reopen.isPending} onClick={() => reopen.mutate()}>
            Reopen scene
          </Button>
        ) : (
          <Button
            size="sm"
            variant="success"
            icon={<Flag className="size-3.5" />}
            disabled={hasDraft || groups.length === 0}
            loading={complete.isPending}
            onClick={() => complete.mutate()}
          >
            Complete scene
          </Button>
        )}
      </header>
      <ErrorText error={complete.error} />

      <div className="grid flex-1 gap-6 p-6 xl:grid-cols-[minmax(0,1fr)_minmax(380px,40%)]">
        <div className="space-y-4">
          {scene.summary && (
            <Card className="border-emerald-500/30 bg-emerald-500/5 p-4 text-sm text-emerald-100/80">
              <span className="font-semibold text-emerald-300">Scene summary: </span>
              {scene.summary}
            </Card>
          )}
          {groups.map((g) => (
            <GroupCard
              key={g.id}
              group={g}
              project={project}
              castIds={scene.cast_ids}
              focused={focused?.id === g.id}
              onFocus={() => setFocus(g.id)}
              onScene={setScene}
            />
          ))}
          {scene.status !== 'complete' && (
            <NextBlockComposer scene={scene} hasDraft={hasDraft} onScene={(s) => { setScene(s); setFocus(s.groups[s.groups.length - 1]?.id ?? null) }} />
          )}
        </div>
        <aside className="xl:sticky xl:top-20 xl:h-fit">
          <ScenePreview scene={scene} project={project} focusId={focused?.id} onFocus={setFocus} />
        </aside>
      </div>

      {editOpen && <EditSceneModal scene={scene} project={project} onClose={() => setEditOpen(false)} onScene={setScene} />}
    </div>
  )
}

function EditSceneModal({
  scene,
  project,
  onClose,
  onScene,
}: {
  scene: SceneDetail
  project: ProjectDetail
  onClose: () => void
  onScene: (s: SceneDetail) => void
}) {
  const [form, setForm] = useState<SceneFormValue>({
    title: scene.title,
    location_id: scene.location_id,
    cast_ids: scene.cast_ids,
    goal: scene.goal,
    outline: scene.outline,
  })
  const save = useMutation({
    mutationFn: async () => {
      await api.patch(`/scenes/${scene.id}`, form)
      return api.get<SceneDetail>(`/scenes/${scene.id}`)
    },
    onSuccess: (s) => {
      onScene(s)
      onClose()
    },
  })
  return (
    <Modal open onClose={onClose} title="Scene setup">
      <SceneForm value={form} onChange={setForm} project={project} />
      <ErrorText error={save.error} />
      <div className="mt-4 flex justify-end">
        <Button variant="primary" loading={save.isPending} onClick={() => save.mutate()}>
          Save
        </Button>
      </div>
    </Modal>
  )
}

function NextBlockComposer({ scene, hasDraft, onScene }: { scene: SceneDetail; hasDraft: boolean; onScene: (s: SceneDetail) => void }) {
  const [guidance, setGuidance] = useState('')
  const [size, setSize] = useState(5)
  const next = useMutation({
    mutationFn: () => api.post<SceneDetail>(`/scenes/${scene.id}/groups/next`, { guidance, size }),
    onSuccess: (s) => {
      onScene(s)
      setGuidance('')
    },
  })
  const first = scene.groups.length === 0
  return (
    <Card className="border-dashed p-4">
      {scene.llm_suggests_complete && !hasDraft && (
        <p className="mb-3 rounded-lg bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300">
          The writer thinks the scene goal has been reached. You can complete the scene, or keep going.
        </p>
      )}
      <div className="flex flex-col gap-3 md:flex-row">
        <Input
          value={guidance}
          onChange={(e) => setGuidance(e.target.value)}
          placeholder={first ? "Director's note for the opening (optional)" : "Director's note for the next block (optional), e.g. 'Rowan teases Mira about her glasses'"}
          onKeyDown={(e) => e.key === 'Enter' && !hasDraft && next.mutate()}
        />
        <Select className="md:w-32" value={size} onChange={(e) => setSize(Number(e.target.value))}>
          {[2, 3, 4, 5, 6, 8, 10].map((n) => (
            <option key={n} value={n}>
              ~{n} lines
            </option>
          ))}
        </Select>
        <Button variant="primary" className="shrink-0" icon={<Sparkles className="size-4" />} disabled={hasDraft} loading={next.isPending} onClick={() => next.mutate()}>
          {first ? 'Write opening' : 'Write next block'}
        </Button>
      </div>
      {hasDraft && <p className="mt-2 text-xs text-zinc-500">Approve or delete the current draft block first.</p>}
      <ErrorText error={next.error} />
    </Card>
  )
}

function speakerOptions(project: ProjectDetail, castIds: number[]): Character[] {
  const cast = project.characters.filter((c) => castIds.includes(c.id))
  return cast.length ? cast : project.characters
}

function GroupCard({
  group,
  project,
  castIds,
  focused,
  onFocus,
  onScene,
}: {
  group: DialogueGroup
  project: ProjectDetail
  castIds: number[]
  focused: boolean
  onFocus: () => void
  onScene: (s: SceneDetail) => void
}) {
  const [lines, setLines] = useState<DialogueLine[]>(group.lines)
  const [guidance, setGuidance] = useState('')
  const [lineBusy, setLineBusy] = useState<number | null>(null)
  useEffect(() => setLines(group.lines), [group.lines])

  const isDraft = group.status === 'draft'
  const dirty = JSON.stringify(lines) !== JSON.stringify(group.lines)
  const speakers = speakerOptions(project, castIds)
  const colorOf = (id: number | null) => project.characters.find((c) => c.id === id)?.color

  const saveLines = useMutation({ mutationFn: () => api.put<SceneDetail>(`/groups/${group.id}/lines`, lines), onSuccess: onScene })
  const regenerate = useMutation({
    mutationFn: async () => {
      return api.post<SceneDetail>(`/groups/${group.id}/regenerate`, { guidance })
    },
    onSuccess: (s) => {
      onScene(s)
      setGuidance('')
    },
  })
  const approve = useMutation({
    mutationFn: async () => {
      if (dirty) await api.put(`/groups/${group.id}/lines`, lines)
      return api.post<SceneDetail>(`/groups/${group.id}/approve`, { auto_images: true })
    },
    onSuccess: onScene,
  })
  const unapprove = useMutation({ mutationFn: () => api.post<SceneDetail>(`/groups/${group.id}/unapprove`), onSuccess: onScene })
  const remove = useMutation({ mutationFn: () => api.del<SceneDetail>(`/groups/${group.id}`), onSuccess: onScene })
  const regenLine = useMutation({
    mutationFn: async (lineId: number) => {
      setLineBusy(lineId)
      if (dirty) await api.put(`/groups/${group.id}/lines`, lines)
      return api.post<SceneDetail>(`/lines/${lineId}/regenerate`, { guidance })
    },
    onSuccess: onScene,
    onSettled: () => setLineBusy(null),
  })

  const update = (i: number, patch: Partial<DialogueLine>) => setLines(lines.map((l, j) => (j === i ? { ...l, ...patch } : l)))
  const move = (i: number, d: number) => {
    const next = [...lines]
    const [item] = next.splice(i, 1)
    next.splice(i + d, 0, item)
    setLines(next)
  }
  const error = saveLines.error || regenerate.error || approve.error || regenLine.error || unapprove.error
  const busy = regenerate.isPending || approve.isPending

  return (
    <Card className={clsx('transition', focused ? 'border-accent/60 ring-1 ring-accent/30' : '')}>
      <div className="flex items-center gap-2 border-b border-ink-700/70 px-4 py-2.5" onClick={onFocus}>
        <span className="text-sm font-semibold text-zinc-200">Block {group.order + 1}</span>
        <Badge status={group.status} />
        {group.guidance && <span className="truncate text-xs text-zinc-500 italic">"{group.guidance}"</span>}
        <div className="ml-auto flex items-center gap-1">
          {!isDraft && (
            <Button size="sm" variant="ghost" icon={<Undo2 className="size-3.5" />} loading={unapprove.isPending} onClick={() => unapprove.mutate()}>
              Back to draft
            </Button>
          )}
          <Button size="sm" variant="ghost" icon={<Trash2 className="size-3.5" />} onClick={() => confirm('Delete this block and its images?') && remove.mutate()} />
        </div>
      </div>

      <div className="space-y-1.5 p-3" onClick={onFocus}>
        {lines.map((l, i) => (
          <div key={l.id ?? `new-${i}`} className="group flex gap-2 rounded-lg p-1.5 hover:bg-ink-850">
            <div className="w-32 shrink-0 space-y-1">
              <select
                className="w-full rounded-md border border-transparent bg-transparent py-0.5 text-sm font-semibold hover:border-ink-700 focus:border-accent focus:outline-none"
                style={{ color: colorOf(l.speaker_id) ?? '#a1a1aa' }}
                value={l.speaker_id ?? ''}
                onChange={(e) => {
                  const id = e.target.value ? Number(e.target.value) : null
                  update(i, { speaker_id: id, speaker_name: project.characters.find((c) => c.id === id)?.name ?? 'Narrator' })
                }}
              >
                <option value="">Narrator</option>
                {speakers.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
              <input
                className="w-full rounded-md border border-transparent bg-transparent px-1 text-[11px] text-zinc-500 hover:border-ink-700 focus:border-accent focus:outline-none"
                value={l.emotion}
                placeholder="emotion"
                onChange={(e) => update(i, { emotion: e.target.value })}
              />
            </div>
            <div className="min-w-0 flex-1">
              <textarea
                rows={1}
                className={clsx(
                  'w-full resize-none rounded-md [field-sizing:content] border border-transparent bg-transparent px-1.5 py-0.5 text-sm leading-relaxed hover:border-ink-700 focus:border-accent focus:outline-none',
                  l.speaker_id === null ? 'text-zinc-400 italic' : 'text-zinc-100',
                )}
                value={l.text}
                onChange={(e) => update(i, { text: e.target.value })}
              />
              <input
                className="w-full rounded-md border border-transparent bg-transparent px-1.5 text-[11px] text-zinc-500 italic hover:border-ink-700 focus:border-accent focus:outline-none"
                value={l.action}
                placeholder="stage direction"
                onChange={(e) => update(i, { action: e.target.value })}
              />
            </div>
            <div className="flex shrink-0 flex-col gap-0.5 opacity-0 transition group-hover:opacity-100">
              {l.id && (
                <button title="Rewrite this line" className="rounded p-1 text-zinc-500 hover:bg-ink-700 hover:text-violet-300" onClick={() => regenLine.mutate(l.id!)}>
                  {lineBusy === l.id ? <Spinner className="size-3.5" /> : <RefreshCw className="size-3.5" />}
                </button>
              )}
              {i > 0 && (
                <button className="rounded p-1 text-zinc-500 hover:bg-ink-700" onClick={() => move(i, -1)}>
                  <ArrowUp className="size-3.5" />
                </button>
              )}
              {i < lines.length - 1 && (
                <button className="rounded p-1 text-zinc-500 hover:bg-ink-700" onClick={() => move(i, 1)}>
                  <ArrowDown className="size-3.5" />
                </button>
              )}
              <button className="rounded p-1 text-zinc-500 hover:bg-ink-700 hover:text-red-300" onClick={() => setLines(lines.filter((_, j) => j !== i))}>
                <Trash2 className="size-3.5" />
              </button>
            </div>
          </div>
        ))}
        <div className="flex items-center gap-2 pt-1">
          <Button
            size="sm"
            variant="ghost"
            icon={<Plus className="size-3.5" />}
            onClick={() => setLines([...lines, { speaker_id: null, speaker_name: 'Narrator', text: '', emotion: '', action: '' }])}
          >
            Add line
          </Button>
          {dirty && (
            <Button size="sm" icon={<Save className="size-3.5" />} loading={saveLines.isPending} onClick={() => saveLines.mutate()}>
              Save edits
            </Button>
          )}
        </div>
      </div>

      {isDraft ? (
        <div className="flex flex-col gap-2 border-t border-ink-700/70 p-3 md:flex-row">
          <Input value={guidance} onChange={(e) => setGuidance(e.target.value)} placeholder="Note for rewriting (optional): 'more tension', 'Mira should lie'..." />
          <Button className="shrink-0" icon={<Sparkles className="size-4" />} loading={regenerate.isPending} disabled={busy} onClick={() => regenerate.mutate()}>
            Rewrite block
          </Button>
          <Button className="shrink-0" variant="success" icon={<CheckCircle2 className="size-4" />} loading={approve.isPending} disabled={busy || lines.length === 0} onClick={() => approve.mutate()}>
            Approve & illustrate
          </Button>
        </div>
      ) : (
        <Illustration group={group} onScene={onScene} />
      )}
      {error && (
        <div className="px-3 pb-3">
          <ErrorText error={error} />
        </div>
      )}
    </Card>
  )
}

function Illustration({ group, onScene }: { group: DialogueGroup; onScene: (s: SceneDetail) => void }) {
  const { data: jobs = [] } = useJobs()
  const [showPrompt, setShowPrompt] = useState(false)
  const [prompt, setPrompt] = useState(group.prompt)
  const [negative, setNegative] = useState(group.negative_prompt)
  const [count, setCount] = useState(2)
  const [zoom, setZoom] = useState<ImageAsset | null>(null)
  const [inpaint, setInpaint] = useState<ImageAsset | null>(null)
  useEffect(() => {
    setPrompt(group.prompt)
    setNegative(group.negative_prompt)
  }, [group.prompt, group.negative_prompt])

  const groupJobs = jobs.filter((j) => j.payload?.target === 'group' && j.payload?.id === group.id)
  const active = groupJobs.filter(isActive)
  const lastFailed = groupJobs[0]?.status === 'failed' ? groupJobs[0] : null
  const promptDirty = prompt !== group.prompt || negative !== group.negative_prompt

  const savePrompt = useMutation({
    mutationFn: () => api.patch<SceneDetail>(`/groups/${group.id}`, { prompt, negative_prompt: negative }),
    onSuccess: onScene,
  })
  const generate = useMutation({
    mutationFn: async (extra: Record<string, unknown> = {}) => {
      if (promptDirty) onScene(await api.patch<SceneDetail>(`/groups/${group.id}`, { prompt, negative_prompt: negative }))
      return api.post(`/groups/${group.id}/images`, { count, ...extra })
    },
  })
  const reshoot = useMutation({ mutationFn: () => api.post<SceneDetail>(`/groups/${group.id}/shot`), onSuccess: onScene })
  const select = useMutation({
    mutationFn: (imageId: number | null) => api.post<SceneDetail>(`/groups/${group.id}/select`, { image_id: imageId }),
    onSuccess: onScene,
  })
  const del = useMutation({
    mutationFn: async (id: number) => {
      await api.del(`/images/${id}`)
      return api.get<SceneDetail>(`/scenes/${group.scene_id}`)
    },
    onSuccess: onScene,
  })

  return (
    <div className="space-y-3 border-t border-ink-700/70 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold tracking-wide text-zinc-400 uppercase">Illustration</span>
        <button className="text-xs text-zinc-500 underline-offset-2 hover:text-zinc-300 hover:underline" onClick={() => setShowPrompt(!showPrompt)}>
          {showPrompt ? 'hide' : 'art direction'}
        </button>
        <div className="ml-auto flex items-center gap-2">
          <Button size="sm" variant="ghost" icon={<Sparkles className="size-3.5" />} loading={reshoot.isPending} onClick={() => reshoot.mutate()}>
            Re-direct shot
          </Button>
          <Select className="h-7 w-20 text-xs" value={count} onChange={(e) => setCount(Number(e.target.value))}>
            {[1, 2, 3, 4, 6].map((n) => (
              <option key={n} value={n}>
                x{n}
              </option>
            ))}
          </Select>
          <Button size="sm" variant="primary" icon={<ImagePlus className="size-3.5" />} loading={generate.isPending} onClick={() => generate.mutate({})}>
            Generate
          </Button>
        </div>
      </div>

      {group.warnings.length > 0 && (
        <ul className="space-y-1 text-[11px] text-amber-300/80">
          {group.warnings.map((w) => (
            <li key={w}>- {w}</li>
          ))}
        </ul>
      )}

      {showPrompt && (
        <div className="space-y-2 rounded-lg bg-ink-850 p-3">
          {group.shot.camera && (
            <p className="text-[11px] text-zinc-500">
              Shot: {group.shot.camera} | {group.shot.lighting} | {group.shot.mood}
            </p>
          )}
          <Textarea rows={4} className="text-xs" value={prompt} onChange={(e) => setPrompt(e.target.value)} />
          <Textarea rows={2} className="text-xs" value={negative} onChange={(e) => setNegative(e.target.value)} placeholder="negative prompt" />
          {promptDirty && (
            <Button size="sm" icon={<Save className="size-3.5" />} loading={savePrompt.isPending} onClick={() => savePrompt.mutate()}>
              Save prompt
            </Button>
          )}
        </div>
      )}

      {active.map((j) => (
        <div key={j.id} className="space-y-1">
          <Progress value={j.progress} />
          <p className="text-[11px] text-zinc-500">{j.status === 'queued' ? 'Waiting for GPU...' : j.message}</p>
        </div>
      ))}
      {lastFailed && !active.length && <ErrorText error={lastFailed.error} />}
      <ErrorText error={generate.error || reshoot.error} />

      {group.images.length > 0 && (
        <div className="grid grid-cols-2 gap-2 lg:grid-cols-3">
          {group.images.map((img) => {
            const selected = group.selected_image_id === img.id
            return (
              <div
                key={img.id}
                className={clsx(
                  'group relative cursor-pointer overflow-hidden rounded-lg border-2 transition',
                  selected ? 'border-emerald-500 shadow-lg shadow-emerald-900/40' : 'border-transparent hover:border-ink-600',
                )}
                onClick={() => select.mutate(selected ? null : img.id)}
              >
                <img src={fileUrl(img.path)} className="aspect-video w-full object-cover" loading="lazy" />
                {selected && <CheckCircle2 className="absolute top-1.5 left-1.5 size-5 text-emerald-400 drop-shadow" />}
                {img.meta?.mode && img.meta.mode !== 'txt2img' ? (
                  <span className="absolute bottom-1.5 left-1.5 rounded bg-black/70 px-1.5 text-[10px] text-zinc-300">{String(img.meta.mode)}</span>
                ) : null}
                <div className="absolute top-1.5 right-1.5 flex gap-1 opacity-0 transition group-hover:opacity-100" onClick={(e) => e.stopPropagation()}>
                  <IconBtn title="View" onClick={() => setZoom(img)} icon={<ZoomIn className="size-3.5" />} />
                  <IconBtn
                    title="Variation (img2img)"
                    onClick={() => generate.mutate({ mode: 'img2img', source_image_id: img.id, strength: 0.5 })}
                    icon={<Wand2 className="size-3.5" />}
                  />
                  <IconBtn title="Inpaint" onClick={() => setInpaint(img)} icon={<Brush className="size-3.5" />} />
                  <IconBtn title="Same seed" onClick={() => generate.mutate({ seed: img.seed, count: 1 })} icon={<Copy className="size-3.5" />} />
                  <IconBtn title="Delete" onClick={() => del.mutate(img.id)} icon={<Trash2 className="size-3.5" />} danger />
                </div>
              </div>
            )
          })}
        </div>
      )}
      {group.images.length > 0 && !group.selected_image_id && (
        <p className="text-[11px] text-zinc-500">Click an image to pick it for this block.</p>
      )}

      <Lightbox path={zoom?.path ?? null} caption={zoom ? `seed ${zoom.seed} - ${zoom.prompt}` : ''} onClose={() => setZoom(null)} />
      {inpaint && (
        <MaskEditor
          image={inpaint}
          defaultPrompt={group.prompt}
          busy={generate.isPending}
          onClose={() => setInpaint(null)}
          onSubmit={async (mask, p) => {
            await generate.mutateAsync({ mask, source_image_id: inpaint.id, prompt: p, count: 1, strength: 0.85 })
            setInpaint(null)
          }}
        />
      )}
    </div>
  )
}

function IconBtn({ icon, onClick, title, danger }: { icon: React.ReactNode; onClick: () => void; title: string; danger?: boolean }) {
  return (
    <button
      title={title}
      onClick={onClick}
      className={clsx('rounded-md bg-black/70 p-1.5 text-zinc-300 backdrop-blur transition', danger ? 'hover:text-red-300' : 'hover:text-white')}
    >
      {icon}
    </button>
  )
}

function ScenePreview({
  scene,
  project,
  focusId,
  onFocus,
}: {
  scene: SceneDetail
  project: ProjectDetail
  focusId?: number
  onFocus: (id: number) => void
}) {
  const [lineIdx, setLineIdx] = useState(0)
  const groups = scene.groups
  const gi = Math.max(0, groups.findIndex((g) => g.id === focusId))
  const group = groups[gi]
  useEffect(() => setLineIdx(0), [focusId])

  const image = useMemo(() => {
    if (!group) return null
    const sel = group.images.find((i) => i.id === group.selected_image_id) ?? group.images[0]
    if (sel) return sel.path
    for (let k = gi - 1; k >= 0; k--) {
      const g = groups[k]
      const prev = g.images.find((i) => i.id === g.selected_image_id) ?? g.images[0]
      if (prev) return prev.path
    }
    return project.locations.find((l) => l.id === scene.location_id)?.image_path || null
  }, [group, gi, groups, project, scene.location_id])

  if (!group) {
    return (
      <Card className="p-4">
        <VNPreview image={project.locations.find((l) => l.id === scene.location_id)?.image_path || null} line={null} />
        <p className="mt-3 text-center text-sm text-zinc-500">Write the opening block to start the scene.</p>
      </Card>
    )
  }
  const line = group.lines[lineIdx]
  const color = project.characters.find((c) => c.id === line?.speaker_id)?.color

  const advance = (d: number) => {
    const ni = lineIdx + d
    if (ni >= 0 && ni < group.lines.length) return setLineIdx(ni)
    const ng = groups[gi + d]
    if (ng) {
      onFocus(ng.id)
      if (d < 0) setTimeout(() => setLineIdx(ng.lines.length - 1), 0)
    }
  }

  return (
    <Card className="space-y-3 p-4">
      <VNPreview
        image={image}
        line={line ? { speaker: line.speaker_name, speaker_id: line.speaker_id, text: line.text, action: line.action } : null}
        color={color}
        onClick={() => advance(1)}
      />
      <div className="flex items-center justify-between text-xs text-zinc-500">
        <Button size="sm" variant="ghost" icon={<ChevronLeft className="size-4" />} onClick={() => advance(-1)} />
        <span>
          Block {gi + 1}/{groups.length} - line {Math.min(lineIdx + 1, group.lines.length)}/{group.lines.length}
        </span>
        <Button size="sm" variant="ghost" icon={<ChevronRight className="size-4" />} onClick={() => advance(1)} />
      </div>
      <div className="flex gap-1.5 overflow-x-auto pb-1">
        {groups.map((g) => {
          const img = g.images.find((i) => i.id === g.selected_image_id) ?? g.images[0]
          return (
            <button
              key={g.id}
              onClick={() => onFocus(g.id)}
              className={clsx('relative h-12 w-20 shrink-0 overflow-hidden rounded-md border-2', g.id === group.id ? 'border-accent' : 'border-ink-700')}
            >
              {img ? <img src={fileUrl(img.path)} className="h-full w-full object-cover" /> : <div className="checker h-full w-full" />}
              <span className="absolute bottom-0 left-0 bg-black/70 px-1 text-[9px] text-zinc-300">{g.order + 1}</span>
            </button>
          )
        })}
      </div>
    </Card>
  )
}
