import { Brush, Eraser, RotateCcw } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { fileUrl } from '../lib/api'
import type { ImageAsset } from '../lib/types'
import { Button, Field, Input, Modal } from './ui'

/** Paint the area to regenerate. Produces a white-on-black PNG mask at the image's native size. */
export function MaskEditor({
  image,
  defaultPrompt,
  onClose,
  onSubmit,
  busy,
}: {
  image: ImageAsset
  defaultPrompt: string
  onClose: () => void
  onSubmit: (mask: string, prompt: string) => void
  busy?: boolean
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [brush, setBrush] = useState(48)
  const [erase, setErase] = useState(false)
  const [prompt, setPrompt] = useState(defaultPrompt)
  const drawing = useRef(false)

  useEffect(() => {
    const c = canvasRef.current
    if (!c) return
    c.width = image.width
    c.height = image.height
  }, [image])

  const paint = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!drawing.current) return
    const c = canvasRef.current!
    const rect = c.getBoundingClientRect()
    const x = ((e.clientX - rect.left) / rect.width) * c.width
    const y = ((e.clientY - rect.top) / rect.height) * c.height
    const ctx = c.getContext('2d')!
    ctx.globalCompositeOperation = erase ? 'destination-out' : 'source-over'
    ctx.fillStyle = 'rgba(167,139,250,0.55)'
    ctx.beginPath()
    ctx.arc(x, y, (brush * c.width) / rect.width / 2, 0, Math.PI * 2)
    ctx.fill()
  }

  const exportMask = () => {
    const src = canvasRef.current!
    const out = document.createElement('canvas')
    out.width = src.width
    out.height = src.height
    const ctx = out.getContext('2d')!
    ctx.fillStyle = '#000'
    ctx.fillRect(0, 0, out.width, out.height)
    const data = src.getContext('2d')!.getImageData(0, 0, src.width, src.height)
    const mask = ctx.getImageData(0, 0, out.width, out.height)
    for (let i = 0; i < data.data.length; i += 4) {
      if (data.data[i + 3] > 0) {
        mask.data[i] = mask.data[i + 1] = mask.data[i + 2] = 255
      }
    }
    ctx.putImageData(mask, 0, 0)
    return out.toDataURL('image/png')
  }

  return (
    <Modal open onClose={onClose} title="Inpaint - paint the area to regenerate" wide>
      <div className="space-y-4">
        <div className="relative mx-auto w-fit">
          <img src={fileUrl(image.path)} className="max-h-[60vh] rounded-lg" draggable={false} />
          <canvas
            ref={canvasRef}
            className="absolute inset-0 h-full w-full cursor-crosshair touch-none rounded-lg"
            onPointerDown={(e) => {
              drawing.current = true
              e.currentTarget.setPointerCapture(e.pointerId)
              paint(e)
            }}
            onPointerMove={paint}
            onPointerUp={() => (drawing.current = false)}
          />
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button size="sm" variant={erase ? 'secondary' : 'primary'} icon={<Brush className="size-3.5" />} onClick={() => setErase(false)}>
            Brush
          </Button>
          <Button size="sm" variant={erase ? 'primary' : 'secondary'} icon={<Eraser className="size-3.5" />} onClick={() => setErase(true)}>
            Eraser
          </Button>
          <label className="flex items-center gap-2 text-xs text-zinc-400">
            Size
            <input type="range" min={8} max={160} value={brush} onChange={(e) => setBrush(Number(e.target.value))} className="accent-violet-500" />
          </label>
          <Button
            size="sm"
            variant="ghost"
            icon={<RotateCcw className="size-3.5" />}
            onClick={() => {
              const c = canvasRef.current!
              c.getContext('2d')!.clearRect(0, 0, c.width, c.height)
            }}
          >
            Clear
          </Button>
        </div>
        <Field label="Prompt for the masked area">
          <Input value={prompt} onChange={(e) => setPrompt(e.target.value)} />
        </Field>
        <div className="flex justify-end">
          <Button variant="primary" loading={busy} onClick={() => onSubmit(exportMask(), prompt)}>
            Inpaint
          </Button>
        </div>
      </div>
    </Modal>
  )
}
