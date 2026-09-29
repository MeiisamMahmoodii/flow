import clsx from 'clsx'
import type { ProjectDetail } from '../lib/types'
import { Field, Input, Select, Textarea } from './ui'

export interface SceneFormValue {
  title: string
  location_id: number | null
  cast_ids: number[]
  goal: string
  outline: string
}

export function SceneForm({
  value,
  onChange,
  project,
}: {
  value: SceneFormValue
  onChange: (v: SceneFormValue) => void
  project: ProjectDetail
}) {
  const toggle = (id: number) =>
    onChange({
      ...value,
      cast_ids: value.cast_ids.includes(id) ? value.cast_ids.filter((c) => c !== id) : [...value.cast_ids, id],
    })
  return (
    <div className="space-y-4">
      <Field label="Title">
        <Input value={value.title} onChange={(e) => onChange({ ...value, title: e.target.value })} placeholder="First Shift" />
      </Field>
      <Field label="Location">
        <Select
          value={value.location_id ?? ''}
          onChange={(e) => onChange({ ...value, location_id: e.target.value ? Number(e.target.value) : null })}
        >
          <option value="">None</option>
          {project.locations.map((l) => (
            <option key={l.id} value={l.id}>
              {l.name}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Cast" hint="Leave empty to make the whole cast available.">
        <div className="flex flex-wrap gap-2">
          {project.characters.map((c) => (
            <button
              type="button"
              key={c.id}
              onClick={() => toggle(c.id)}
              className={clsx(
                'rounded-full border px-3 py-1 text-xs transition',
                value.cast_ids.includes(c.id)
                  ? 'border-accent bg-accent/20 text-violet-100'
                  : 'border-ink-700 text-zinc-400 hover:border-ink-600',
              )}
            >
              <span className="mr-1.5 inline-block size-2 rounded-full" style={{ background: c.color }} />
              {c.name}
            </button>
          ))}
          {project.characters.length === 0 && <span className="text-xs text-zinc-500">No characters yet.</span>}
        </div>
      </Field>
      <Field label="Scene goal" hint="What must have happened by the end of the scene.">
        <Textarea rows={2} value={value.goal} onChange={(e) => onChange({ ...value, goal: e.target.value })} />
      </Field>
      <Field label="Outline (optional)">
        <Textarea rows={3} value={value.outline} onChange={(e) => onChange({ ...value, outline: e.target.value })} />
      </Field>
    </div>
  )
}
