import React, { useMemo, useState } from "react";
import { api } from "../api.js";
import Icon from "../components/Icons.jsx";
import {
  Badge,
  Button,
  Callout,
  ConfirmDialog,
  EmptyState,
  Field,
  IconButton,
  LoadingBlock,
  Modal,
  PageHead,
  useToast,
} from "../components/ui.jsx";
import { formatDate, safeHost } from "../utils.js";

const EMPTY = {
  name: "",
  website_url: "",
  description: "",
  target_audience: "",
  product_category: "",
  unique_selling_proposition: "",
  features: "",
  pricing_info: "",
  brand_voice: "",
  marketing_objectives: "",
  disclosure_statement: "",
  restricted_claims: "",
};

export default function Projects({ projects, refresh, setProjectId, projectsLoading, projectsError }) {
  const toast = useToast();
  const [modal, setModal] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [busy, setBusy] = useState(false);

  const active = projects.filter((project) => !project.is_archived);
  const archived = projects.filter((project) => project.is_archived);
  const totals = useMemo(() => ({
    drafts: projects.reduce((sum, project) => sum + (project.draft_count || 0), 0),
    published: projects.reduce((sum, project) => sum + (project.published_count || 0), 0),
    communities: projects.reduce((sum, project) => sum + (project.subreddit_count || 0), 0),
  }), [projects]);

  const toggleArchive = async () => {
    if (!confirm?.project) return;
    const project = confirm.project;
    setBusy(true);
    try {
      await api.patch(`/api/projects/${project.id}`, { is_archived: !project.is_archived });
      toast.success(project.is_archived ? "Project restored" : "Project archived", project.is_archived ? `${project.name} is active again.` : `${project.name} is hidden from active workspace views; its history is preserved.`);
      setConfirm(null);
      refresh();
    } catch (error) {
      toast.error("Could not update project", error.message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!confirm?.project) return;
    setBusy(true);
    try {
      await api.delete(`/api/projects/${confirm.project.id}`);
      toast.success("Project deleted", "The project and its schedule plan were removed.");
      setConfirm(null);
      refresh();
    } catch (error) {
      toast.error("Could not delete project", error.message);
    } finally {
      setBusy(false);
    }
  };

  if (projectsLoading) {
    return (
      <div className="page">
        <PageHead eyebrow="Projects" title="Your work, separated." />
        <div className="grid grid-2">
          <div className="card"><div className="card-body"><LoadingBlock lines={4} height={24} /></div></div>
          <div className="card"><div className="card-body"><LoadingBlock lines={4} height={24} /></div></div>
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <PageHead
        eyebrow="Projects"
        title="One brief per product."
        description="A project is the honest context Gemini writes from: the product, the audience, the voice, the disclosure, and the claims you must never make. RedditPilot ships empty — this is all your own data."
        actions={(
          <>
            <Badge tone="neutral" dot>{active.length} active</Badge>
            <Button variant="primary" icon="plus" onClick={() => setModal({ mode: "create" })}>New project</Button>
          </>
        )}
      />

      {projectsError && <Callout tone="danger" title="Could not load projects" icon="alertCircle">{projectsError}</Callout>}

      {projects.length === 0 ? (
        <div className="card">
          <EmptyState
            icon="folder"
            title="No projects yet"
            text="Start with one product or side project. A focused brief produces better drafts than a vague description of everything you do."
            actions={<Button variant="primary" icon="plus" onClick={() => setModal({ mode: "create" })}>Create your first project</Button>}
          />
          <div className="grid grid-3" style={{ padding: "0 22px 24px" }}>
            {[
              ["Be specific", "What it is, who it is for, and why it exists — in plain language."],
              ["Set boundaries", "Disclosure text and restricted claims keep the compliance engine honest."],
              ["Keep it current", "Drafts use this brief every time, so update it when the product changes."],
            ].map(([title, text]) => (
              <div key={title} className="card" style={{ background: "rgba(0,0,0,.12)", padding: 16 }}>
                <div className="serif" style={{ fontSize: 15, marginBottom: 4 }}>{title}</div>
                <p className="field-hint">{text}</p>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <>
          <div className="stat-grid" style={{ marginBottom: 16 }}>
            <div className="stat">
              <span className="stat-label">Active projects</span>
              <span className="stat-value">{active.length}</span>
              <span className="stat-meta">{archived.length} archived</span>
            </div>
            <div className="stat">
              <span className="stat-label">Communities</span>
              <span className="stat-value">{totals.communities}</span>
              <span className="stat-meta">Across all projects</span>
            </div>
            <div className="stat">
              <span className="stat-label">Drafts</span>
              <span className="stat-value">{totals.drafts}</span>
              <span className="stat-meta">AI and manual combined</span>
            </div>
            <div className="stat">
              <span className="stat-label">Published</span>
              <span className="stat-value">{totals.published}</span>
              <span className="stat-meta">Recorded publications</span>
            </div>
          </div>

          <div className="grid grid-2">
            {active.map((project) => <ProjectCard key={project.id} project={project} onEdit={() => setModal({ mode: "edit", project })} onToggle={() => setConfirm({ type: "archive", project })} onDelete={() => setConfirm({ type: "delete", project })} />)}
          </div>

          {archived.length > 0 && (
            <div style={{ marginTop: 28 }}>
              <div className="row-between" style={{ marginBottom: 12 }}>
                <div>
                  <h2 className="section-title" style={{ fontSize: 18 }}>Archived</h2>
                  <p className="field-hint">Preserved for the audit trail and hidden from active selection.</p>
                </div>
                <Badge tone="neutral">{archived.length}</Badge>
              </div>
              <div className="grid grid-2">
                {archived.map((project) => <ProjectCard key={project.id} project={project} archived onEdit={() => setModal({ mode: "edit", project })} onToggle={() => setConfirm({ type: "archive", project })} onDelete={() => setConfirm({ type: "delete", project })} />)}
              </div>
            </div>
          )}
        </>
      )}

      {modal && (
        <ProjectModal
          mode={modal.mode}
          project={modal.project}
          onClose={() => setModal(null)}
          onSaved={(saved) => {
            setModal(null);
            refresh();
            toast.success(modal.mode === "create" ? "Project created" : "Project updated", `${saved?.name || "Your project"} is ready for the Content Studio. Select it in the header to focus the workspace.`);
          }}
        />
      )}

      <ConfirmDialog
        open={confirm?.type === "archive"}
        onClose={() => setConfirm(null)}
        onConfirm={toggleArchive}
        busy={busy}
        tone={confirm?.project?.is_archived ? "primary" : "danger"}
        icon={confirm?.project?.is_archived ? "restore" : "archive"}
        title={confirm?.project?.is_archived ? `Restore ${confirm?.project?.name}?` : `Archive ${confirm?.project?.name}?`}
        message={confirm?.project?.is_archived
          ? "The project returns to active views. Its drafts, schedule and history are unchanged."
          : "The project is hidden from active views and its weekly plan stops materializing new slots. Existing drafts and publication history are preserved. You can restore it later."}
        confirmLabel={confirm?.project?.is_archived ? "Restore project" : "Archive project"}
      />

      <ConfirmDialog
        open={confirm?.type === "delete"}
        onClose={() => setConfirm(null)}
        onConfirm={remove}
        busy={busy}
        tone="danger"
        icon="trash"
        title={`Delete ${confirm?.project?.name}?`}
        message="Projects with any drafts, publications or communities cannot be deleted — archive them instead to preserve the record. Deleting an empty project also removes its schedule plan."
        confirmLabel="Delete permanently"
      />
    </div>
  );
}

function ProjectCard({ project, archived, onEdit, onToggle, onDelete }) {
  return (
    <div className="card" style={{ opacity: archived ? 0.82 : 1 }}>
      <div className="card-body">
        <div className="row" style={{ alignItems: "flex-start", gap: 10 }}>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div className="row" style={{ gap: 7 }}>
              <h2 className="card-title" style={{ fontSize: 20 }}>{project.name}</h2>
              {archived ? <Badge tone="neutral">Archived</Badge> : <Badge tone="sage" dot>Active</Badge>}
            </div>
            <div className="row" style={{ gap: 6, marginTop: 3 }}>
              <a href={project.website_url} target="_blank" rel="noreferrer" className="field-hint row" style={{ gap: 4 }}>
                <Icon name="globe" size={11} />{safeHost(project.website_url)}
              </a>
              {project.product_category && <><span className="muted" style={{ fontSize: 10 }}>·</span><span className="field-hint">{project.product_category}</span></>}
            </div>
          </div>
          <div className="row" style={{ gap: 2 }}>
            <IconButton icon="edit" label="Edit project" size="sm" onClick={onEdit} />
            <IconButton icon={archived ? "restore" : "archive"} label={archived ? "Restore project" : "Archive project"} size="sm" onClick={onToggle} />
            <IconButton icon="trash" label="Delete project" size="sm" onClick={onDelete} />
          </div>
        </div>

        <p className="field-hint line-2" style={{ marginTop: 10, minHeight: 34 }}>{project.description || "No description recorded yet."}</p>

        <div className="grid grid-3" style={{ gap: 8, marginTop: 12 }}>
          {[
            ["Communities", project.subreddit_count || 0],
            ["Drafts", project.draft_count || 0],
            ["Published", project.published_count || 0],
          ].map(([label, value]) => (
            <div key={label} style={{ borderTop: "1px solid var(--line-soft)", paddingTop: 8 }}>
              <div className="section-label">{label}</div>
              <div className="serif" style={{ fontSize: 21 }}>{value}</div>
            </div>
          ))}
        </div>

        <div className="row" style={{ gap: 5, marginTop: 12 }}>
          {project.brand_voice ? <Badge tone="neutral">Voice recorded</Badge> : <Badge tone="amber">Voice missing</Badge>}
          {project.disclosure_statement ? <Badge tone="sage">Disclosure ready</Badge> : <Badge tone="amber">No disclosure</Badge>}
          {project.restricted_claims ? <Badge tone="neutral">Claims guardrails</Badge> : null}
        </div>
      </div>
      <div className="card-footer-actions" style={{ justifyContent: "space-between" }}>
        <span className="field-hint">Created {formatDate(project.created_at)}</span>
        <Button size="sm" variant="outline" icon="edit" onClick={onEdit}>Edit brief</Button>
      </div>
    </div>
  );
}

function ProjectModal({ mode, project, onClose, onSaved }) {
  const toast = useToast();
  const [form, setForm] = useState(project ? {
    name: project.name,
    website_url: project.website_url,
    description: project.description || "",
    target_audience: project.target_audience || "",
    product_category: project.product_category || "",
    unique_selling_proposition: project.unique_selling_proposition || "",
    features: project.features || "",
    pricing_info: project.pricing_info || "",
    brand_voice: project.brand_voice || "",
    marketing_objectives: project.marketing_objectives || "",
    disclosure_statement: project.disclosure_statement || "",
    restricted_claims: project.restricted_claims || "",
  } : { ...EMPTY });
  const [busy, setBusy] = useState(false);

  const set = (key, value) => setForm((current) => ({ ...current, [key]: value }));

  const submit = async (event) => {
    event?.preventDefault();
    if (form.name.trim().length < 2) return toast.warning("Add a project name", "Use at least two characters.");
    if (!form.website_url.trim()) return toast.warning("Add the website URL", "Gemini uses it to understand the project context.");
    setBusy(true);
    try {
      let saved;
      if (mode === "edit") {
        saved = await api.patch(`/api/projects/${project.id}`, form);
      } else {
        saved = await api.post("/api/projects", form);
      }
      onSaved(saved);
    } catch (error) {
      toast.error("Could not save project", error.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      title={mode === "edit" ? `Edit ${project.name}` : "New project"}
      subtitle="Write as if a careful colleague will use this brief to represent you."
      size="lg"
      busy={busy}
      footer={(
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button variant="primary" icon="check" onClick={submit} loading={busy}>{mode === "edit" ? "Save brief" : "Create project"}</Button>
        </>
      )}
    >
      <form onSubmit={submit}>
        <div className="stack">
          <div>
            <div className="section-label" style={{ marginBottom: 9 }}>Identity</div>
            <div className="form-grid">
              <Field label="Project name"><input className="input" value={form.name} onChange={(event) => set("name", event.target.value)} placeholder="e.g. Lantern Notes" maxLength={160} /></Field>
              <Field label="Website URL" hint="Must include https://"><input className="input" value={form.website_url} onChange={(event) => set("website_url", event.target.value)} placeholder="https://example.com" /></Field>
              <Field label="Category" optional><input className="input" value={form.product_category} onChange={(event) => set("product_category", event.target.value)} placeholder="e.g. Developer tools" maxLength={160} /></Field>
              <Field label="Target audience" optional><input className="input" value={form.target_audience} onChange={(event) => set("target_audience", event.target.value)} placeholder="e.g. Solo developers shipping side projects" /></Field>
              <Field label="Description" optional className="full" hint="What it is and why it exists, in two or three plain sentences.">
                <textarea className="textarea" rows={3} value={form.description} onChange={(event) => set("description", event.target.value)} placeholder="A calm note-taking app for engineers who think in outlines." />
              </Field>
            </div>
          </div>

          <hr className="divider" />

          <div>
            <div className="section-label" style={{ marginBottom: 9 }}>Positioning</div>
            <div className="form-grid">
              <Field label="Unique selling proposition" optional className="full">
                <textarea className="textarea" rows={2} value={form.unique_selling_proposition} onChange={(event) => set("unique_selling_proposition", event.target.value)} placeholder="The specific thing this does better — without superlatives." />
              </Field>
              <Field label="Features worth mentioning" optional>
                <textarea className="textarea" rows={3} value={form.features} onChange={(event) => set("features", event.target.value)} placeholder="One per line. Only what is true today." />
              </Field>
              <Field label="Pricing" optional>
                <textarea className="textarea" rows={3} value={form.pricing_info} onChange={(event) => set("pricing_info", event.target.value)} placeholder="Free tier, paid plans, or 'not launched yet'." />
              </Field>
              <Field label="Marketing objectives" optional className="full">
                <textarea className="textarea" rows={2} value={form.marketing_objectives} onChange={(event) => set("marketing_objectives", event.target.value)} placeholder="e.g. Find five early users who care about a calmer workflow, not mass traffic." />
              </Field>
            </div>
          </div>

          <hr className="divider" />

          <div>
            <div className="section-label" style={{ marginBottom: 9 }}>Voice & boundaries</div>
            <div className="form-grid">
              <Field label="Brand voice" optional className="full" hint="How should the writing sound? What should it avoid?">
                <textarea className="textarea" rows={2} value={form.brand_voice} onChange={(event) => set("brand_voice", event.target.value)} placeholder="Plain, specific, self-aware. No hype, no exclamation marks, no growth-hacking language." />
              </Field>
              <Field label="Default disclosure" optional className="full" hint="Included in generated drafts when the post mentions your project.">
                <textarea className="textarea" rows={2} value={form.disclosure_statement} onChange={(event) => set("disclosure_statement", event.target.value)} placeholder="Disclosure: I built this project and I am sharing it here because…" />
              </Field>
              <Field label="Restricted claims" optional className="full" hint="Comma or newline separated. The compliance engine blocks these exact phrases.">
                <textarea className="textarea" rows={2} value={form.restricted_claims} onChange={(event) => set("restricted_claims", event.target.value)} placeholder="e.g. guaranteed results, 10x faster, replaces your accountant" />
              </Field>
            </div>
          </div>

          <Callout tone="info" icon="shield">
            This brief is sent to Gemini with each generation. It is never sent to Reddit. Keep it accurate — the model cannot verify claims for you.
          </Callout>
        </div>
      </form>
    </Modal>
  );
}
