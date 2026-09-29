import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import './index.css'
import { CharactersPage } from './pages/CharactersPage'
import { JobsPage } from './pages/JobsPage'
import { LocationsPage } from './pages/LocationsPage'
import { PlayPage } from './pages/PlayPage'
import { ProjectPage } from './pages/ProjectPage'
import { ProjectsPage } from './pages/ProjectsPage'
import { SceneEditorPage } from './pages/SceneEditorPage'
import { SettingsPage } from './pages/SettingsPage'

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1 } },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<ProjectsPage />} />
            <Route path="p/:projectId" element={<ProjectPage />} />
            <Route path="p/:projectId/characters" element={<CharactersPage />} />
            <Route path="p/:projectId/locations" element={<LocationsPage />} />
            <Route path="p/:projectId/scenes/:sceneId" element={<SceneEditorPage />} />
            <Route path="jobs" element={<JobsPage />} />
            <Route path="settings" element={<SettingsPage />} />
          </Route>
          <Route path="p/:projectId/play" element={<PlayPage />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
