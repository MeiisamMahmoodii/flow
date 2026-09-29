export interface Project {
  id: number
  name: string
  premise: string
  style_preset: string
  created_at: string
}

export interface RefImage {
  file: string
  caption: string
}

export interface Character {
  id: number
  project_id: number
  name: string
  description: string
  personality: string
  speech_style: string
  appearance: string
  appearance_tags: string
  relationships: string
  color: string
  trigger_word: string
  lora_path: string
  lora_weight: number
  ref_images: RefImage[]
}

export interface Location {
  id: number
  project_id: number
  name: string
  description: string
  tags: string
  image_path: string
}

export interface Scene {
  id: number
  project_id: number
  title: string
  order: number
  location_id: number | null
  cast_ids: number[]
  goal: string
  outline: string
  status: 'drafting' | 'complete'
  summary: string
  llm_suggests_complete: boolean
}

export interface ProjectDetail extends Project {
  characters: Character[]
  locations: Location[]
  scenes: Scene[]
}

export interface DialogueLine {
  id?: number
  order?: number
  speaker_id: number | null
  speaker_name: string
  text: string
  emotion: string
  action: string
}

export interface ImageAsset {
  id: number
  project_id: number | null
  group_id: number | null
  character_id: number | null
  location_id: number | null
  kind: string
  path: string
  prompt: string
  negative_prompt: string
  seed: number
  width: number
  height: number
  backend: string
  meta: Record<string, unknown>
  created_at: string
}

export interface Shot {
  characters?: { id: number; expression: string; pose: string; position: string; outfit: string }[]
  camera?: string
  background?: string
  lighting?: string
  mood?: string
  extra_tags?: string
}

export type GroupStatus = 'draft' | 'approved' | 'imaging' | 'images_ready' | 'done'

export interface DialogueGroup {
  id: number
  scene_id: number
  order: number
  status: GroupStatus
  guidance: string
  shot: Shot
  prompt: string
  negative_prompt: string
  warnings: string[]
  selected_image_id: number | null
  lines: DialogueLine[]
  images: ImageAsset[]
}

export interface SceneDetail extends Scene {
  groups: DialogueGroup[]
}

export interface Job {
  id: number
  kind: string
  status: 'queued' | 'running' | 'done' | 'failed' | 'cancelled'
  progress: number
  message: string
  payload: Record<string, unknown>
  result: Record<string, unknown>
  error: string
  logs: string
  created_at: string
  finished_at: string | null
}

export interface TrainingCheckpoint {
  step: number
  path: string
  samples: string[]
}

export interface TrainingRun {
  id: number
  character_id: number
  job_id: number | null
  status: string
  preset: string
  params: Record<string, number | string>
  checkpoints: TrainingCheckpoint[]
  created_at: string
}

export interface Settings {
  llm_provider: 'ollama' | 'lmstudio' | 'custom'
  llm_base_url: string
  llm_api_key: string
  llm_model: string
  llm_vision_model: string
  llm_temperature: number
  llm_max_tokens: number
  llm_json_mode: boolean
  image_backend: 'diffusers' | 'comfyui'
  checkpoint_dir: string
  default_checkpoint: string
  device: string
  dtype: string
  comfy_url: string
  comfy_lora_dir: string
  comfy_checkpoint: string
  comfy_sampler: string
  comfy_scheduler: string
  style_preset: string
  width: number
  height: number
  steps: number
  cfg: number
  variants: number
  negative_prompt: string
  ip_adapter_repo: string
  ip_adapter_subfolder: string
  ip_adapter_weight: string
  ip_adapter_image_encoder: string
  ip_adapter_scale: number
  captioner: 'wd14' | 'vision_llm'
  wd14_repo: string
  wd14_threshold: number
}

export interface SystemInfo {
  device: { torch: boolean; device: string | null; dtype?: string; gpu?: string; vram_gb?: number; hint?: string }
  backend: { backend: string; available: boolean; loaded_checkpoint?: string | null; hint?: string | null; url?: string }
  style_presets: Record<string, string>
  llm_presets: Record<string, string>
}

export interface Playthrough {
  project: { id: number; name: string; premise: string }
  characters: { id: number; name: string; color: string }[]
  scenes: {
    id: number
    title: string
    summary: string
    status: string
    background: string | null
    groups: {
      id: number
      order: number
      image: string | null
      lines: { speaker_id: number | null; speaker: string; text: string; emotion: string; action: string }[]
    }[]
  }[]
}
