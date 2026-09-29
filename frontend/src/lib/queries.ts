import { useQuery } from '@tanstack/react-query'
import { api } from './api'
import type { ProjectDetail, SceneDetail, Settings, SystemInfo } from './types'

export function useProject(projectId: number | undefined) {
  return useQuery({
    queryKey: ['project', projectId],
    queryFn: () => api.get<ProjectDetail>(`/projects/${projectId}`),
    enabled: !!projectId,
  })
}

export function useScene(sceneId: number | undefined) {
  return useQuery({
    queryKey: ['scene', sceneId],
    queryFn: () => api.get<SceneDetail>(`/scenes/${sceneId}`),
    enabled: !!sceneId,
  })
}

export function useSettings() {
  return useQuery({ queryKey: ['settings'], queryFn: () => api.get<Settings>('/settings') })
}

export function useSystemInfo() {
  return useQuery({ queryKey: ['system'], queryFn: () => api.get<SystemInfo>('/system/info'), staleTime: 30_000 })
}
