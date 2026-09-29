import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Cpu, ImageIcon, MessageSquareText, RefreshCw, Save } from 'lucide-react'
import type { ReactNode } from 'react'
import { useEffect, useState } from 'react'
import { Badge, Button, Card, ErrorText, Field, Input, PageHeader, Select, Textarea } from '../components/ui'
import { api } from '../lib/api'
import { useSettings, useSystemInfo } from '../lib/queries'
import type { Settings } from '../lib/types'

function Section({ icon, title, children, aside }: { icon: ReactNode; title: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <Card className="p-5">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="flex items-center gap-2 font-semibold text-zinc-100 [&>svg]:size-4 [&>svg]:text-accent">
          {icon}
          {title}
        </h2>
        {aside}
      </div>
      <div className="grid gap-4 md:grid-cols-2">{children}</div>
    </Card>
  )
}

export function SettingsPage() {
  const qc = useQueryClient()
  const { data: settings } = useSettings()
  const { data: system, refetch: refetchSystem } = useSystemInfo()
  const [form, setForm] = useState<Settings | null>(null)
  useEffect(() => {
    if (settings) setForm(settings)
  }, [settings])

  const llmModels = useQuery({
    queryKey: ['llm-models', form?.llm_base_url],
    queryFn: () => api.get<string[]>('/llm/models'),
    enabled: !!settings,
    retry: false,
  })
  const imageModels = useQuery({
    queryKey: ['image-models', settings?.image_backend, settings?.checkpoint_dir, settings?.comfy_url],
    queryFn: () => api.get<string[]>('/image/models'),
    enabled: !!settings,
    retry: false,
  })
  const save = useMutation({
    mutationFn: (data: Partial<Settings>) => api.put<Settings>('/settings', data),
    onSuccess: (s) => {
      qc.setQueryData(['settings'], s)
      setForm(s)
      qc.invalidateQueries({ queryKey: ['llm-models'] })
      qc.invalidateQueries({ queryKey: ['image-models'] })
      refetchSystem()
    },
  })
  const test = useMutation({ mutationFn: () => api.post<{ reply: string }>('/llm/test') })

  if (!form) return null
  const set = <K extends keyof Settings>(key: K, value: Settings[K]) => setForm({ ...form, [key]: value })
  const num = (key: keyof Settings) => (e: React.ChangeEvent<HTMLInputElement>) => set(key, Number(e.target.value) as never)

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-8">
      <PageHeader
        title="Settings"
        subtitle="Everything runs locally: the writer via Ollama or LM Studio, images via diffusers or ComfyUI."
        actions={
          <Button variant="primary" icon={<Save className="size-4" />} loading={save.isPending} onClick={() => save.mutate(form)}>
            Save settings
          </Button>
        }
      />
      <ErrorText error={save.error} />

      <Section
        icon={<MessageSquareText />}
        title="Writer model (LLM)"
        aside={
          <Button size="sm" loading={test.isPending} onClick={async () => { await save.mutateAsync(form); test.mutate() }}>
            Test connection
          </Button>
        }
      >
        <Field label="Provider">
          <Select
            value={form.llm_provider}
            onChange={(e) => {
              const p = e.target.value as Settings['llm_provider']
              setForm({ ...form, llm_provider: p, llm_base_url: system?.llm_presets[p] ?? form.llm_base_url })
            }}
          >
            <option value="ollama">Ollama</option>
            <option value="lmstudio">LM Studio</option>
            <option value="custom">Custom OpenAI-compatible</option>
          </Select>
        </Field>
        <Field label="Base URL">
          <Input value={form.llm_base_url} onChange={(e) => set('llm_base_url', e.target.value)} />
        </Field>
        <Field label="Model" hint={llmModels.error ? <span className="text-red-300">{(llmModels.error as Error).message}</span> : 'Uncensored / abliterated models work best for mature fiction.'}>
          <div className="flex gap-2">
            <Select value={form.llm_model} onChange={(e) => set('llm_model', e.target.value)}>
              <option value="">(first available)</option>
              {(llmModels.data ?? []).map((m) => (
                <option key={m}>{m}</option>
              ))}
              {form.llm_model && !llmModels.data?.includes(form.llm_model) && <option>{form.llm_model}</option>}
            </Select>
            <Button icon={<RefreshCw className="size-4" />} onClick={() => llmModels.refetch()} />
          </div>
        </Field>
        <Field label="Vision model (for captions)" hint="e.g. qwen2.5vl, llava, gemma vision - only if captioner is 'vision LLM'.">
          <Select value={form.llm_vision_model} onChange={(e) => set('llm_vision_model', e.target.value)}>
            <option value="">(none)</option>
            {(llmModels.data ?? []).map((m) => (
              <option key={m}>{m}</option>
            ))}
          </Select>
        </Field>
        <Field label={`Temperature: ${form.llm_temperature}`}>
          <input type="range" min={0} max={1.5} step={0.05} value={form.llm_temperature} onChange={num('llm_temperature')} className="mt-2 w-full accent-violet-500" />
        </Field>
        <Field label="Max tokens">
          <Input type="number" value={form.llm_max_tokens} onChange={num('llm_max_tokens')} />
        </Field>
        <label className="flex items-center gap-2 text-sm text-zinc-400">
          <input type="checkbox" checked={form.llm_json_mode} onChange={(e) => set('llm_json_mode', e.target.checked)} className="accent-violet-500" />
          Request JSON mode (disable if your server errors on response_format)
        </label>
        {(test.data || test.error) && (
          <div className="text-sm">
            {test.data ? <span className="text-emerald-400">Model replied: "{test.data.reply}"</span> : <ErrorText error={test.error} />}
          </div>
        )}
      </Section>

      <Section
        icon={<ImageIcon />}
        title="Image generation"
        aside={
          system && (
            <Badge status={system.backend.available ? 'done' : 'failed'}>
              {system.backend.backend} {system.backend.available ? 'ready' : 'unavailable'}
            </Badge>
          )
        }
      >
        <Field label="Backend">
          <Select value={form.image_backend} onChange={(e) => set('image_backend', e.target.value as Settings['image_backend'])}>
            <option value="diffusers">Built-in (diffusers, runs models directly)</option>
            <option value="comfyui">ComfyUI (preset workflows)</option>
          </Select>
        </Field>
        <Field label="Default art style">
          <Select value={form.style_preset} onChange={(e) => set('style_preset', e.target.value)}>
            {Object.entries(system?.style_presets ?? {}).map(([k, label]) => (
              <option key={k} value={k}>
                {label}
              </option>
            ))}
          </Select>
        </Field>
        {form.image_backend === 'diffusers' ? (
          <>
            <Field label="Checkpoint folder" hint="SDXL-family .safetensors files (SDXL, Illustrious, NoobAI, Pony, RealVis...).">
              <Input value={form.checkpoint_dir} onChange={(e) => set('checkpoint_dir', e.target.value)} />
            </Field>
            <Field label="Default checkpoint" hint="Pick from the folder, or type an absolute path / Hugging Face repo id.">
              <Input list="ckpts" value={form.default_checkpoint} onChange={(e) => set('default_checkpoint', e.target.value)} />
              <datalist id="ckpts">
                {(imageModels.data ?? []).map((m) => (
                  <option key={m} value={m} />
                ))}
              </datalist>
            </Field>
            <Field label="Device">
              <Select value={form.device} onChange={(e) => set('device', e.target.value)}>
                <option value="auto">Auto ({system?.device.device ?? '?'})</option>
                <option value="cuda">CUDA (NVIDIA)</option>
                <option value="mps">MPS (Apple Silicon)</option>
                <option value="cpu">CPU</option>
              </Select>
            </Field>
            <Field label="Precision">
              <Select value={form.dtype} onChange={(e) => set('dtype', e.target.value)}>
                <option value="auto">Auto</option>
                <option value="float16">float16</option>
                <option value="bfloat16">bfloat16</option>
                <option value="float32">float32</option>
              </Select>
            </Field>
          </>
        ) : (
          <>
            <Field label="ComfyUI URL">
              <Input value={form.comfy_url} onChange={(e) => set('comfy_url', e.target.value)} />
            </Field>
            <Field label="ComfyUI checkpoint">
              <Select value={form.comfy_checkpoint} onChange={(e) => set('comfy_checkpoint', e.target.value)}>
                <option value="">(first available)</option>
                {(imageModels.data ?? []).map((m) => (
                  <option key={m}>{m}</option>
                ))}
              </Select>
            </Field>
            <Field label="ComfyUI LoRA folder" hint="e.g. ~/ComfyUI/models/loras - trained LoRAs are synced here automatically.">
              <Input value={form.comfy_lora_dir} onChange={(e) => set('comfy_lora_dir', e.target.value)} />
            </Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Sampler">
                <Input value={form.comfy_sampler} onChange={(e) => set('comfy_sampler', e.target.value)} />
              </Field>
              <Field label="Scheduler">
                <Input value={form.comfy_scheduler} onChange={(e) => set('comfy_scheduler', e.target.value)} />
              </Field>
            </div>
          </>
        )}
        {imageModels.error && <ErrorText error={imageModels.error} />}
        <div className="grid grid-cols-2 gap-2">
          <Field label="Width">
            <Input type="number" step={64} value={form.width} onChange={num('width')} />
          </Field>
          <Field label="Height">
            <Input type="number" step={64} value={form.height} onChange={num('height')} />
          </Field>
        </div>
        <div className="grid grid-cols-3 gap-2">
          <Field label="Steps">
            <Input type="number" value={form.steps} onChange={num('steps')} />
          </Field>
          <Field label="CFG">
            <Input type="number" step={0.5} value={form.cfg} onChange={num('cfg')} />
          </Field>
          <Field label="Variants">
            <Input type="number" min={1} max={8} value={form.variants} onChange={num('variants')} />
          </Field>
        </div>
        <Field label="Extra negative prompt" className="md:col-span-2">
          <Textarea rows={2} value={form.negative_prompt} onChange={(e) => set('negative_prompt', e.target.value)} />
        </Field>
      </Section>

      <Section icon={<Cpu />} title="Character consistency">
        <Field label="Captioner for training images">
          <Select value={form.captioner} onChange={(e) => set('captioner', e.target.value as Settings['captioner'])}>
            <option value="wd14">WD14 tagger (anime, fast, offline)</option>
            <option value="vision_llm">Vision LLM via Ollama / LM Studio</option>
          </Select>
        </Field>
        <Field label={`WD14 threshold: ${form.wd14_threshold}`}>
          <input type="range" min={0.2} max={0.8} step={0.05} value={form.wd14_threshold} onChange={num('wd14_threshold')} className="mt-2 w-full accent-violet-500" />
        </Field>
        <Field label={`IP-Adapter strength: ${form.ip_adapter_scale}`} hint="Used for characters without a LoRA (diffusers backend).">
          <input type="range" min={0} max={1} step={0.05} value={form.ip_adapter_scale} onChange={num('ip_adapter_scale')} className="mt-2 w-full accent-violet-500" />
        </Field>
        <Field label="IP-Adapter weights" hint={`${form.ip_adapter_repo} / ${form.ip_adapter_subfolder}`}>
          <Input value={form.ip_adapter_weight} onChange={(e) => set('ip_adapter_weight', e.target.value)} />
        </Field>
      </Section>

      {system && (
        <Card className="p-4 text-xs text-zinc-500">
          <span className="font-medium text-zinc-300">Runtime: </span>
          {system.device.torch
            ? `torch on ${system.device.device} (${system.device.dtype})${system.device.gpu ? ` - ${system.device.gpu}, ${system.device.vram_gb} GB` : ''}`
            : system.device.hint}
          {system.backend.loaded_checkpoint && <span> - loaded: {system.backend.loaded_checkpoint.split('/').pop()}</span>}
          {system.backend.hint && <span className="text-amber-300"> - {system.backend.hint}</span>}
        </Card>
      )}
    </div>
  )
}
