import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, qs } from "./api.js";
import Icon from "./components/Icons.jsx";
import { Button, IconButton, ToastProvider, useToast } from "./components/ui.jsx";
import { useLoad } from "./hooks.js";
import { useLocalStorage } from "./utils.js";
import Overview from "./views/Overview.jsx";
import ContentStudio from "./views/ContentStudio.jsx";
import DraftQueue from "./views/DraftQueue.jsx";
import SubredditManager from "./views/SubredditManager.jsx";
import PublishingCalendar from "./views/PublishingCalendar.jsx";
import PublishedPosts from "./views/PublishedPosts.jsx";
import Analytics from "./views/Analytics.jsx";
import Projects from "./views/Projects.jsx";
import Settings from "./views/Settings.jsx";

export const AppContext = createContext(null);
export const useApp = () => useContext(AppContext);

const NAV = [
  {
    group: "Workspace",
    items: [
      { id: "overview", label: "Overview", icon: "overview" },
      { id: "studio", label: "Content Studio", icon: "studio" },
      { id: "queue", label: "Draft Queue", icon: "queue", badge: true },
    ],
  },
  {
    group: "Publishing",
    items: [
      { id: "communities", label: "Subreddit Manager", icon: "community" },
      { id: "calendar", label: "Publishing Calendar", icon: "calendar" },
      { id: "published", label: "Published Posts", icon: "send" },
      { id: "analytics", label: "Analytics", icon: "chart" },
    ],
  },
  {
    group: "Manage",
    items: [
      { id: "projects", label: "Projects", icon: "folder" },
      { id: "settings", label: "Settings", icon: "settings" },
    ],
  },
];

const TITLES = {
  overview: ["Workspace", "Overview"],
  studio: ["Workspace", "Content Studio"],
  queue: ["Workspace", "Draft Queue"],
  communities: ["Publishing", "Subreddit Manager"],
  calendar: ["Publishing", "Publishing Calendar"],
  published: ["Publishing", "Published Posts"],
  analytics: ["Publishing", "Analytics"],
  projects: ["Manage", "Projects"],
  settings: ["Manage", "Settings"],
};

const VIEWS = {
  overview: Overview,
  studio: ContentStudio,
  queue: DraftQueue,
  communities: SubredditManager,
  calendar: PublishingCalendar,
  published: PublishedPosts,
  analytics: Analytics,
  projects: Projects,
  settings: Settings,
};

function readHash() {
  const hash = window.location.hash.replace(/^#\/?/, "");
  return TITLES[hash] ? hash : "overview";
}

function Shell() {
  const toast = useToast();
  const [view, setView] = useState(readHash);
  const [projectId, setProjectId] = useLocalStorage("redditpilot.project", "");
  const [refreshKey, setRefreshKey] = useState(0);
  const [focusDraft, setFocusDraft] = useState(null);
  const [mobileOpen, setMobileOpen] = useState(false);

  const projectsQuery = useLoad(() => api.get("/api/projects?include_archived=true"));
  const settingsQuery = useLoad(() => api.get("/api/settings"));
  const overviewQuery = useLoad(
    () => api.get(`/api/overview${qs({ project_id: projectId || undefined })}`),
    [projectId, refreshKey]
  );

  const projects = projectsQuery.data?.items || [];
  const settings = settingsQuery.data || null;

  useEffect(() => {
    const onHash = () => setView(readHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    if (!projects.length) return;
    const active = projects.filter((project) => !project.is_archived);
    if (projectId && !projects.some((project) => String(project.id) === String(projectId))) {
      setProjectId(active[0] ? String(active[0].id) : "");
    }
  }, [projects, projectId, setProjectId]);

  const navigate = useCallback((next, options = {}) => {
    if (options.focusDraft !== undefined) setFocusDraft(options.focusDraft);
    if (TITLES[next]) {
      window.location.hash = `#/${next}`;
      setView(next);
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
    setMobileOpen(false);
  }, []);

  const refresh = useCallback(() => {
    setRefreshKey((value) => value + 1);
    projectsQuery.reload();
    settingsQuery.reload();
  }, [projectsQuery, settingsQuery]);

  const refreshAll = refresh;

  useEffect(() => {
    if (overviewQuery.error) {
      // The individual views surface their own errors; keep the shell quiet.
    }
  }, [overviewQuery.error]);

  const pendingCount = overviewQuery.data?.pending_approvals || 0;
  const activeProject = projects.find((project) => String(project.id) === String(projectId));
  const [groupLabel, titleLabel] = TITLES[view];

  const contextValue = useMemo(() => ({
    view,
    navigate,
    projects,
    activeProject,
    projectId,
    setProjectId: (value) => setProjectId(value),
    settings,
    settingsLoading: settingsQuery.loading,
    settingsError: settingsQuery.error,
    reloadSettings: settingsQuery.reload,
    refresh,
    refreshKey,
    refreshAll,
    focusDraft,
    setFocusDraft,
    pendingCount,
    overview: overviewQuery.data,
    reloadOverview: overviewQuery.reload,
    projectsLoading: projectsQuery.loading,
    projectsError: projectsQuery.error,
    reloadProjects: projectsQuery.reload,
  }), [
    view, navigate, projects, activeProject, projectId, setProjectId, settings,
    settingsQuery.loading, settingsQuery.error, settingsQuery.reload, refresh, refreshKey,
    refreshAll, focusDraft, pendingCount, overviewQuery.data, overviewQuery.reload,
    projectsQuery.loading, projectsQuery.error, projectsQuery.reload,
  ]);

  const ViewComponent = VIEWS[view] || Overview;

  return (
    <AppContext.Provider value={contextValue}>
      <div className="app-shell">
        {mobileOpen && (
          <div
            className="mobile-scrim"
            onClick={() => setMobileOpen(false)}
            aria-hidden="true"
          />
        )}
        <aside className={`sidebar ${mobileOpen ? "open" : ""}`} aria-label="Main navigation">
          <div className="sidebar-brand">
            <div className="brand-mark">R</div>
            <div>
              <div className="brand-name">Reddit<em>Pilot</em></div>
              <div className="brand-sub">Editorial workspace</div>
            </div>
            <IconButton
              className="hide-desktop sidebar-close"
              icon="close"
              label="Close menu"
              onClick={() => setMobileOpen(false)}
            />
          </div>
          <div className="sidebar-scroll">
            {NAV.map((group) => (
              <div className="nav-group" key={group.group}>
                <div className="nav-label">{group.group}</div>
                {group.items.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={`nav-item ${view === item.id ? "active" : ""}`}
                    onClick={() => navigate(item.id)}
                  >
                    <Icon name={item.icon} size={16} />
                    <span>{item.label}</span>
                    {item.badge && pendingCount > 0 && <span className="nav-badge">{pendingCount}</span>}
                  </button>
                ))}
              </div>
            ))}
            <div className="nav-group">
              <div className="nav-label">Safety</div>
              <div className="callout" style={{ padding: "10px 11px", fontSize: 10.5, lineHeight: 1.55 }}>
                <Icon name="shield" size={14} />
                <div>Every post needs human approval. Nothing publishes automatically.</div>
              </div>
            </div>
          </div>
          <div className="sidebar-footer">
            <div className="status-line">
              <span className={`dot ${settings?.gemini_key_configured ? "green" : "red"}`} />
              Gemini <strong>{settings?.gemini_key_configured ? "configured" : "not configured"}</strong>
            </div>
            <div className="status-line">
              <span className={`dot ${settings?.publishing_mode === "api" ? "ember" : "green"}`} />
              Mode <strong>{settings?.publishing_mode === "api" ? "API" : "Manual"}</strong>
            </div>
            <div className="status-line">
              <span className={`dot ${settings?.scheduling_paused ? "red" : "green"}`} />
              Scheduler <strong>{settings?.scheduling_paused ? "paused" : "active"}</strong>
            </div>
          </div>
        </aside>

        <div className="main-shell">
          <header className="topbar">
            <IconButton
              className="mobile-menu"
              icon="menu"
              label="Open menu"
              onClick={() => setMobileOpen(true)}
            />
            <div className="topbar-context">
              <div className="topbar-eyebrow">{groupLabel} · RedditPilot</div>
              <div className="topbar-title">{titleLabel}</div>
            </div>
            <div className="topbar-actions">
              <div className="topbar-project">
                <label htmlFor="global-project">Project</label>
                <select
                  id="global-project"
                  className="project-select"
                  value={projectId || ""}
                  onChange={(event) => setProjectId(event.target.value)}
                >
                  <option value="">All projects</option>
                  {projects.filter((project) => !project.is_archived).map((project) => (
                    <option key={project.id} value={project.id}>{project.name}</option>
                  ))}
                </select>
              </div>
              <IconButton
                icon="refresh"
                label="Refresh data"
                onClick={() => {
                  refreshAll();
                  toast.info("Refreshed", "Latest data loaded from the local server.");
                }}
              />
              <Button variant="primary" size="sm" icon="plus" onClick={() => navigate("studio")}>
                New draft
              </Button>
            </div>
          </header>

          <main className="content">
            {projectsQuery.error && (
              <div className="callout danger" style={{ marginBottom: 20 }}>
                <Icon name="alertCircle" size={17} />
                <div>
                  <span className="callout-title">Cannot reach the local server</span>
                  {projectsQuery.error} Start the backend with <span className="mono">scripts\start.bat</span> or{" "}
                  <span className="mono">uvicorn app.main:app</span>, then refresh.
                </div>
              </div>
            )}
            <ViewComponent
              key={view}
              projects={projects}
              projectId={projectId}
              setProjectId={setProjectId}
              activeProject={activeProject}
              settings={settings}
              reloadSettings={settingsQuery.reload}
              refresh={refresh}
              refreshKey={refreshKey}
              focusDraft={focusDraft}
              setFocusDraft={setFocusDraft}
              navigate={navigate}
              projectsLoading={projectsQuery.loading}
              projectsError={projectsQuery.error}
            />
          </main>
        </div>
      </div>
    </AppContext.Provider>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <Shell />
    </ToastProvider>
  );
}
