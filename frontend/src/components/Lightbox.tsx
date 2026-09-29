import { X } from 'lucide-react'
import { useEffect } from 'react'
import { fileUrl } from '../lib/api'

export function Lightbox({ path, caption, onClose }: { path: string | null; caption?: string; onClose: () => void }) {
  useEffect(() => {
    if (!path) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [path, onClose])
  if (!path) return null
  return (
    <div className="fixed inset-0 z-[60] flex flex-col items-center justify-center bg-black/90 p-6" onClick={onClose}>
      <button className="absolute top-4 right-4 rounded-full p-2 text-zinc-400 hover:bg-white/10 hover:text-white">
        <X className="size-5" />
      </button>
      <img src={fileUrl(path)} className="max-h-[85vh] max-w-full rounded-lg object-contain shadow-2xl" />
      {caption && <p className="mt-4 max-w-3xl text-center text-xs text-zinc-400">{caption}</p>}
    </div>
  )
}
