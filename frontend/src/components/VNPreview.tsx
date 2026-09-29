import clsx from 'clsx'
import { ImageOff } from 'lucide-react'
import { fileUrl } from '../lib/api'

export interface PreviewLine {
  speaker: string
  speaker_id: number | null
  text: string
  action?: string
}

export function VNPreview({
  image,
  line,
  color,
  onClick,
  className,
  footer,
}: {
  image: string | null
  line: PreviewLine | null
  color?: string
  onClick?: () => void
  className?: string
  footer?: React.ReactNode
}) {
  const narrator = !line || line.speaker_id === null
  return (
    <div
      className={clsx('relative aspect-video w-full overflow-hidden rounded-xl bg-black select-none [container-type:inline-size]', onClick && 'cursor-pointer', className)}
      onClick={onClick}
    >
      {image ? (
        <img src={fileUrl(image)} className="absolute inset-0 h-full w-full object-cover" />
      ) : (
        <div className="checker absolute inset-0 flex items-center justify-center text-zinc-600">
          <ImageOff className="size-10" />
        </div>
      )}
      {line && (
        <div className="absolute inset-x-[3%] bottom-[4%]">
          {!narrator && (
            <div
              className="mb-[-1px] ml-4 inline-block rounded-t-lg bg-black/80 px-4 py-1 text-[clamp(11px,1.6cqw,18px)] font-semibold"
              style={{ color: color ?? '#e9d5ff' }}
            >
              {line.speaker}
            </div>
          )}
          <div className="rounded-xl border border-white/10 bg-gradient-to-b from-black/80 to-black/90 px-5 py-3 shadow-2xl backdrop-blur-sm">
            {line.action && <p className="mb-1 text-[clamp(10px,1.2cqw,14px)] text-zinc-400 italic">({line.action})</p>}
            <p className={clsx('font-serif text-[clamp(12px,1.8cqw,20px)] leading-relaxed', narrator ? 'text-zinc-300 italic' : 'text-zinc-50')}>
              {line.text}
            </p>
          </div>
        </div>
      )}
      {footer}
    </div>
  )
}
