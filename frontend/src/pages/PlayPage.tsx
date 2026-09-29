import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Eye, EyeOff } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Spinner } from '../components/ui'
import { VNPreview } from '../components/VNPreview'
import { api } from '../lib/api'
import type { Playthrough } from '../lib/types'

interface Frame {
  sceneTitle: string
  image: string | null
  line: Playthrough['scenes'][number]['groups'][number]['lines'][number] | null
  titleCard?: boolean
}

export function PlayPage() {
  const pid = Number(useParams().projectId)
  const [drafts, setDrafts] = useState(false)
  const { data, isLoading } = useQuery({
    queryKey: ['playthrough', pid, drafts],
    queryFn: () => api.get<Playthrough>(`/projects/${pid}/playthrough?drafts=${drafts}`),
  })
  const [idx, setIdx] = useState(0)

  const frames = useMemo<Frame[]>(() => {
    if (!data) return []
    const out: Frame[] = []
    let lastImage: string | null = null
    for (const scene of data.scenes) {
      if (!scene.groups.length) continue
      lastImage = scene.background ?? lastImage
      out.push({ sceneTitle: scene.title, image: scene.groups[0].image ?? lastImage, line: null, titleCard: true })
      for (const g of scene.groups) {
        lastImage = g.image ?? lastImage
        for (const line of g.lines) out.push({ sceneTitle: scene.title, image: lastImage, line })
      }
    }
    return out
  }, [data])

  const next = useCallback(() => setIdx((i) => Math.min(i + 1, frames.length)), [frames.length])
  const prev = useCallback(() => setIdx((i) => Math.max(i - 1, 0)), [])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (['ArrowRight', ' ', 'Enter'].includes(e.key)) next()
      if (e.key === 'ArrowLeft') prev()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [next, prev])

  const colors = useMemo(() => Object.fromEntries((data?.characters ?? []).map((c) => [c.id, c.color])), [data])
  const frame = frames[idx]

  return (
    <div className="flex h-full flex-col bg-black">
      <div className="flex items-center gap-3 px-4 py-2 text-xs text-zinc-500">
        <Link to={`/p/${pid}`} className="flex items-center gap-1 hover:text-zinc-200">
          <ArrowLeft className="size-4" /> Back to editor
        </Link>
        <span className="flex-1 text-center">{data?.project.name}</span>
        <button className="flex items-center gap-1 hover:text-zinc-200" onClick={() => { setDrafts(!drafts); setIdx(0) }}>
          {drafts ? <Eye className="size-4" /> : <EyeOff className="size-4" />} {drafts ? 'Including drafts' : 'Approved only'}
        </button>
        <span>
          {Math.min(idx + 1, frames.length)} / {frames.length}
        </span>
      </div>
      <div className="flex flex-1 items-center justify-center p-4">
        {isLoading ? (
          <Spinner className="size-6" />
        ) : frames.length === 0 ? (
          <p className="text-zinc-500">Nothing to play yet - approve some dialogue blocks first.</p>
        ) : idx >= frames.length ? (
          <div className="text-center">
            <p className="font-serif text-3xl text-zinc-200">Fin</p>
            <button className="mt-4 text-sm text-violet-300 hover:underline" onClick={() => setIdx(0)}>
              Play again
            </button>
          </div>
        ) : (
          <div className="w-full max-w-[min(100%,calc((100vh-6rem)*16/9))]">
            <VNPreview
              image={frame.image}
              line={frame.line ? { speaker: frame.line.speaker, speaker_id: frame.line.speaker_id, text: frame.line.text, action: frame.line.action } : null}
              color={frame.line?.speaker_id ? colors[frame.line.speaker_id] : undefined}
              onClick={next}
              className="rounded-none shadow-2xl"
              footer={
                frame.titleCard ? (
                  <div className="absolute inset-0 flex items-center justify-center bg-black/60">
                    <h2 className="font-serif text-[clamp(20px,4cqw,48px)] text-zinc-100 drop-shadow-lg">{frame.sceneTitle}</h2>
                  </div>
                ) : null
              }
            />
            <p className="mt-2 text-center text-[11px] text-zinc-600">Click, Space or Right arrow to advance. Left arrow to go back.</p>
          </div>
        )}
      </div>
    </div>
  )
}
