import clsx from 'clsx'
import { BookOpen, Clapperboard, FolderOpen, ListChecks, MapPin, Play, Settings, Sparkles, Users } from 'lucide-react'
import type { ReactNode } from 'react'
import { NavLink, Outlet, useParams } from 'react-router-dom'
import { isActive, useJobSocket, useJobs } from '../lib/jobs'
import { useProject } from '../lib/queries'
import { Progress } from './ui'

function NavItem({ to, icon, children, end, badge }: { to: string; icon: ReactNode; children: ReactNode; end?: boolean; badge?: ReactNode }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        clsx(
          'flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors',
          isActive ? 'bg-accent/15 text-violet-200' : 'text-zinc-400 hover:bg-ink-800 hover:text-zinc-100',
        )
      }
    >
      <span className="[&>svg]:size-4">{icon}</span>
      <span className="flex-1">{children}</span>
      {badge}
    </NavLink>
  )
}

function ActiveJobs() {
  const { data: jobs = [] } = useJobs()
  const active = jobs.filter(isActive).slice(0, 3)
  if (!active.length) return null
  return (
    <div className="fixed right-4 bottom-4 z-40 w-80 space-y-2">
      {active.map((j) => (
        <NavLink
          key={j.id}
          to="/jobs"
          className="block rounded-xl border border-ink-700 bg-ink-900/95 p-3 shadow-2xl backdrop-blur hover:border-accent/50"
        >
          <div className="mb-1.5 flex items-center justify-between text-xs">
            <span className="font-medium text-zinc-200">{j.kind.replace('_', ' ')}</span>
            <span className="text-zinc-500">{j.status === 'queued' ? 'queued' : `${Math.round(j.progress * 100)}%`}</span>
          </div>
          <Progress value={j.progress} />
          <p className="mt-1.5 truncate text-[11px] text-zinc-500">{j.message}</p>
        </NavLink>
      ))}
    </div>
  )
}

export function Layout() {
  useJobSocket()
  const { projectId } = useParams()
  const pid = projectId ? Number(projectId) : undefined
  const { data: project } = useProject(pid)
  const { data: jobs = [] } = useJobs()
  const activeCount = jobs.filter(isActive).length

  return (
    <div className="flex h-full">
      <aside className="flex w-60 shrink-0 flex-col border-r border-ink-800 bg-ink-900/60 p-3">
        <NavLink to="/" className="mb-6 flex items-center gap-2 px-2 pt-1">
          <div className="flex size-8 items-center justify-center rounded-lg bg-gradient-to-br from-violet-500 to-fuchsia-500">
            <Sparkles className="size-4 text-white" />
          </div>
          <div>
            <div className="text-sm font-semibold text-zinc-100">VN Flow</div>
            <div className="text-[11px] text-zinc-500">local visual novel studio</div>
          </div>
        </NavLink>

        <nav className="space-y-1">
          <NavItem to="/" end icon={<FolderOpen />}>
            Projects
          </NavItem>
        </nav>

        {pid && (
          <div className="mt-6">
            <div className="mb-2 truncate px-3 text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
              {project?.name ?? 'Project'}
            </div>
            <nav className="space-y-1">
              <NavItem to={`/p/${pid}`} end icon={<Clapperboard />}>
                Scenes
              </NavItem>
              <NavItem to={`/p/${pid}/characters`} icon={<Users />}>
                Characters
              </NavItem>
              <NavItem to={`/p/${pid}/locations`} icon={<MapPin />}>
                Locations
              </NavItem>
              <NavItem to={`/p/${pid}/play`} icon={<Play />}>
                Play through
              </NavItem>
            </nav>
            {project && project.scenes.length > 0 && (
              <div className="mt-4 space-y-0.5">
                <div className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-zinc-600">Scenes</div>
                {project.scenes.map((s, i) => (
                  <NavLink
                    key={s.id}
                    to={`/p/${pid}/scenes/${s.id}`}
                    className={({ isActive }) =>
                      clsx(
                        'flex items-center gap-2 truncate rounded-md px-3 py-1.5 text-xs',
                        isActive ? 'bg-ink-800 text-zinc-100' : 'text-zinc-500 hover:text-zinc-200',
                      )
                    }
                  >
                    <BookOpen className="size-3 shrink-0" />
                    <span className="truncate">
                      {i + 1}. {s.title}
                    </span>
                  </NavLink>
                ))}
              </div>
            )}
          </div>
        )}

        <nav className="mt-auto space-y-1 border-t border-ink-800 pt-3">
          <NavItem
            to="/jobs"
            icon={<ListChecks />}
            badge={
              activeCount > 0 && (
                <span className="rounded-full bg-accent-strong px-1.5 text-[10px] font-semibold text-white">{activeCount}</span>
              )
            }
          >
            Jobs
          </NavItem>
          <NavItem to="/settings" icon={<Settings />}>
            Settings
          </NavItem>
        </nav>
      </aside>
      <main className="min-w-0 flex-1 overflow-y-auto">
        <Outlet />
      </main>
      <ActiveJobs />
    </div>
  )
}
