import React, { useEffect, useMemo, useState } from "react";
import { api, qs } from "../api.js";
import Icon from "../components/Icons.jsx";
import {
  Badge,
  Button,
  Callout,
  EmptyState,
  Field,
  PageHead,
  ScoreDots,
  StatusBadge,
  useToast,
} from "../components/ui.jsx";
import { useLoad } from "../hooks.js";
import { formatDateTime, truncate } from "../utils.js";

const FALLBACK_OBJECTIVES = [
  "Introduce a new project",
  "Share a useful resource",
  "Ask for constructive feedback",
  "Share a development story",
  "Discuss an interesting technical challenge",
  "Present a project launch",
  "Share a lesson learned",
];

const FALLBACK_POST_TYPES = [
  "Text post", "Discussion", "Question", "Project showcase", "Tutorial", "Feedback request",
];

export default function ContentStudio({ projects, projectId, settings, navigate, refresh }) {
  const toast = useToast();
  const meta = useLoad(() => api.get("/api/meta"));
  const objectives = meta.data?.objectives || FALLBACK_OBJECTIVES;
  const postTypes = meta.data?.post_types || FALLBACK_POST_TYPES;

  const projectsAvailable = projects.filter((project) => !project.is_archived);
  const [form, setForm] = useState({
    project_id: "",
    subreddit_id: "",
    objective: FALLBACK_OBJECTIVES[0],
    topic: "",
    post_type: "Text post",
    link_preference: "none",
    additional_notes: "",
  });
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);

  const communityQuery = useLoad(
    () => api.get(`/api/subreddits${qs({ project_id: form.project_id || undefined })}`),
    [form.project_id],
    { skip: !form.project_id }
  );
  const recentQuery = useLoad(() => api.get("/api/drafts?limit=6"), []);

  const communities = communityQuery.data?.items || [];
  const selectedCommunity = communities.find((row) => String(row.id) === String(form.subreddit_id));
  const selectedProject = projectsAvailable.find((project) => String(project.id) === String(form.project_id));

  useEffect(() => {
    if (form.project_id || !projectsAvailable.length) return;
    const preferred = projectsAvailable.find((project) => String(project.id) === String(projectId)) || projectsAvailable[0];
    setForm((current) => ({ ...current, project_id: String(preferred.id) }));
  }, [projectsAvailable, projectId, form.project_id]);

  useEffect(() => {
    if (!form.project_id) return;
    if (!communities.length) {
      if (form.subreddit_id) setForm((current) => ({ ...current, subreddit_id: "" }));
      return;
    }
    const stillValid = communities.some((row) => String(row.id) === String(form.subreddit_id));
    if (!stillValid) {
      const preferred = communities.find((row) => row.approval_status !== "prohibited" && row.approval_status !== "not_recommended") || communities[0];
      setForm((current) => ({ ...current, subreddit_id: String(preferred.id) }));
    }
  }, [communities, form.project_id, form.subreddit_id]);

  useEffect(() => {
    if (projectId && projectsAvailable.some((project) => String(project.id) === String(projectId))) {
      setForm((current) => ({ ...current, project_id: String(projectId) }));
    }
  }, [projectId, projectsAvailable.length]);

  const set = (key, value) => setForm((current) => ({ ...current, [key]: value }));

  const updateProject = (value) => {
    setForm((current) => ({ ...current, project_id: value, subreddit_id: "" }));
    setResult(null);
  };

  const generate = async (event) => {
    event.preventDefault();
    if (!form.project_id) return toast.warning("Choose a project", "Create a project before generating a draft.");
    if (!form.subreddit_id) return toast.warning("Choose a community", "Add a subreddit to this project first.");
    if (form.topic.trim().length < 3) return toast.warning("Add a topic", "Give Gemini a specific idea to work from.");
    setBusy(true);
    try {
      const draft = await api.post("/api/drafts/generate", {
        project_id: Number(form.project_id),
        subreddit_id: Number(form.subreddit_id),
        objective: form.objective,
        topic: form.topic.trim(),
        post_type: form.post_type,
        link_preference: form.link_preference,
        additional_notes: form.additional_notes.trim(),
      });
      setResult(draft);
      recentQuery.reload();
      refresh();
      toast.success("Draft generated", "It is waiting in the queue as Pending Review. Nothing has been approved.");
    } catch (error) {
      toast.error("Generation failed", error.message);
    } finally {
      setBusy(false);
    }
  };

  const reset = () => {
    setResult(null);
    setForm((current) => ({ ...current, topic: "", additional_notes: "", link_preference: "none" }));
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const linkDisabled = selectedCommunity?.self_promotion_policy === "prohibited";

  const checklist = useMemo(() => [
    ["Specific", "One concrete idea, not a product announcement."],
    ["Useful alone", "The post should still help someone who never clicks a link."],
    ["Honest", "Disclose your relationship in plain language."],
    ["Community-native", "Written for this subreddit, not cross-posted everywhere."],
  ], []);

  if (!projects.length) {
    return (
      <div className="page">
        <PageHead eyebrow="Content Studio" title="Write something worth reading." description="The studio needs a project and at least one community before it can generate a draft." />
        <div className="card">
          <EmptyState
            icon="studio"
            title="Set up your workspace first"
            text="Create a project and add a subreddit. Gemini uses the project brief and the community's recorded rules to draft something specific."
            actions={<Button variant="primary" icon="folder" onClick={() => navigate("projects")}>Create a project</Button>}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <PageHead
        eyebrow="Content Studio"
        title="Draft with intent."
        description="Give Gemini a specific angle, the community, and the constraints. The output is always a Pending Review draft — never an approval, never a post."
        actions={(
          <>
            <Badge tone="ember" dot>Human approval required</Badge>
            <Button variant="outline" icon="queue" onClick={() => navigate("queue")}>Open queue</Button>
          </>
        )}
      />

      {!settings?.gemini_key_configured && (
        <Callout tone="warning" title="Gemini is not configured" icon="key">
          Add an API key in Settings, or set <span className="mono">GEMINI_API_KEY</span> in <span className="mono">.env</span>, before generating.
          {" "}<button type="button" className="link-btn" onClick={() => navigate("settings")}>Open settings</button>
        </Callout>
      )}

      <div className="studio-grid" style={{ marginTop: settings?.gemini_key_configured ? 0 : 16 }}>
        <form className="card" onSubmit={generate}>
          <div className="card-head">
            <div>
              <h2 className="card-title">The brief</h2>
              <div className="card-sub">What should this post be about?</div>
            </div>
            <Icon name="studio" size={17} style={{ color: "var(--accent)" }} />
          </div>
          <div className="card-body">
            <div className="stack">
              <div className="form-grid">
                <Field label="Project">
                  <select className="select" value={form.project_id} onChange={(event) => updateProject(event.target.value)}>
                    <option value="" disabled>Select a project</option>
                    {projectsAvailable.map((project) => (
                      <option key={project.id} value={project.id}>{project.name}</option>
                    ))}
                  </select>
                </Field>
                <Field label="Community">
                  <select
                    className="select"
                    value={form.subreddit_id}
                    onChange={(event) => { set("subreddit_id", event.target.value); setResult(null); }}
                  >
                    <option value="" disabled>{communities.length ? "Select a community" : "No communities yet"}</option>
                    {communities.map((community) => (
                      <option key={community.id} value={community.id}>
                        r/{community.name}
                      </option>
                    ))}
                  </select>
                </Field>
              </div>

              {communityQuery.data && communities.length === 0 && (
                <Callout tone="warning" title="No communities in this project">
                  Add the subreddit you want to participate in, and record its self-promotion rules first.
                  {" "}<button type="button" className="link-btn" onClick={() => navigate("communities")}>Add community</button>
                </Callout>
              )}

              {selectedCommunity && (
                <div className="row" style={{ gap: 6 }}>
                  <StatusBadge status={selectedCommunity.approval_status} />
                  <Badge tone="neutral">Promotion: {selectedCommunity.self_promotion_policy.replaceAll("_", " ")}</Badge>
                  <Badge tone="neutral">Links: {selectedCommunity.links_policy.replaceAll("_", " ")}</Badge>
                  {!selectedCommunity.last_rules_verified_at && <Badge tone="amber">Rules unverified</Badge>}
                </div>
              )}

              <div className="form-grid">
                <Field label="Objective">
                  <select className="select" value={form.objective} onChange={(event) => set("objective", event.target.value)}>
                    {objectives.map((objective) => <option key={objective} value={objective}>{objective}</option>)}
                  </select>
                </Field>
                <Field label="Post type">
                  <select className="select" value={form.post_type} onChange={(event) => set("post_type", event.target.value)}>
                    {postTypes.map((type) => <option key={type} value={type}>{type}</option>)}
                  </select>
                </Field>
              </div>

              <Field
                label="Topic or angle"
                hint={`${form.topic.length}/1000 · Be specific. “What I learned rebuilding our onboarding in a weekend” beats “my app”.`}
              >
                <textarea
                  className="textarea"
                  maxLength={1000}
                  rows={4}
                  value={form.topic}
                  onChange={(event) => set("topic", event.target.value)}
                  placeholder="A concrete story, lesson, question, or resource — and why this community would care."
                />
              </Field>

              <Field
                label="Project link"
                hint={
                  linkDisabled
                    ? `r/${selectedCommunity?.name} prohibits promotional content. Links are disabled.`
                    : "Links are optional. A post that only exists to drive traffic will be blocked by compliance."
                }
              >
                <div className="segmented">
                  {[
                    ["none", "No link"],
                    ["optional", "Optional link"],
                    ["preferred", "Include project link"],
                  ].map(([value, label]) => (
                    <button
                      key={value}
                      type="button"
                      className={form.link_preference === value ? "active" : ""}
                      onClick={() => set("link_preference", value)}
                      disabled={linkDisabled && value !== "none"}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </Field>

              <Field label="Additional notes" optional hint="Tone, constraints, a detail to include, what to avoid.">
                <textarea
                  className="textarea"
                  rows={3}
                  maxLength={2000}
                  value={form.additional_notes}
                  onChange={(event) => set("additional_notes", event.target.value)}
                  placeholder="e.g. Mention the migration failed twice. Keep it under 350 words."
                />
              </Field>
            </div>
          </div>
          <div className="card-footer-actions">
            <Button type="button" variant="ghost" onClick={reset} disabled={busy}>Clear</Button>
            <Button type="submit" variant="primary" icon="sparkles" loading={busy}>
              {busy ? "Writing…" : "Generate with Gemini"}
            </Button>
          </div>
          <div className="card-foot">
            AI output is stored as <strong style={{ color: "var(--text-soft)" }}>Pending Review</strong>. A human must review, edit, and approve the exact version.
          </div>
        </form>

        <div className="stack">
          {busy && !result && (
            <div className="card">
              <div className="loading-bar" />
              <div className="card-body">
                <div className="stack-sm">
                  <div className="skeleton" style={{ height: 26, width: "78%" }} />
                  <div className="skeleton" style={{ height: 13, width: "42%" }} />
                  <div className="skeleton" style={{ height: 12, marginTop: 14 }} />
                  <div className="skeleton" style={{ height: 12, width: "92%" }} />
                  <div className="skeleton" style={{ height: 12, width: "86%" }} />
                  <div className="skeleton" style={{ height: 12, width: "64%" }} />
                </div>
                <p className="field-hint mt-20">Gemini is drafting against the project brief and the community rules you recorded.</p>
              </div>
            </div>
          )}

          {result ? (
            <div className="card">
              <div className="card-head">
                <div>
                  <div className="row" style={{ gap: 7, marginBottom: 4 }}>
                    <StatusBadge status={result.status} />
                    <Badge tone="neutral">{result.model || "Gemini"}</Badge>
                  </div>
                  <h2 className="card-title">Draft #{result.id}</h2>
                  <div className="card-sub">r/{result.subreddit_name} · {result.post_type}</div>
                </div>
                <Button size="sm" variant="outline" icon="refresh" onClick={reset}>New brief</Button>
              </div>
              <div className="card-body">
                <div className="preview-body">
                  <h3 className="preview-title">{result.title}</h3>
                  <p>{result.body}</p>
                  {result.disclosure && <div className="preview-disclosure">{result.disclosure}</div>}
                  {result.link_url && (
                    <div className="row" style={{ marginTop: 12, gap: 6 }}>
                      <Icon name="link" size={12} style={{ color: "var(--muted)" }} />
                      <span className="mono truncate" style={{ color: "var(--blue)" }}>{result.link_url}</span>
                    </div>
                  )}
                </div>

                <div className="grid grid-2" style={{ marginTop: 14, gap: 10 }}>
                  <div className="card" style={{ background: "rgba(0,0,0,.14)", padding: "11px 13px" }}>
                    <div className="section-label" style={{ marginBottom: 5 }}>Why it belongs</div>
                    <p className="field-hint" style={{ color: "var(--text-soft)" }}>{result.relevance || "No relevance statement returned."}</p>
                  </div>
                  <div className="card" style={{ background: "rgba(0,0,0,.14)", padding: "11px 13px" }}>
                    <div className="row-between" style={{ marginBottom: 5 }}>
                      <span className="section-label">Promotional intensity</span>
                      <ScoreDots value={result.promotional_intensity || 0} />
                    </div>
                    <p className="field-hint">
                      {result.compliance?.blockers ? `${result.compliance.blockers} blocker(s) need resolving.` : "No compliance blockers at generation time."}
                    </p>
                  </div>
                </div>

                {(result.compliance?.issues || []).length > 0 && (
                  <div className="issue-list mt-12">
                    {(result.compliance.issues || []).slice(0, 4).map((issue) => (
                      <div key={issue.code} className={`issue ${issue.severity}`}>
                        <Icon name={issue.severity === "blocker" ? "alertCircle" : issue.severity === "warning" ? "alert" : "info"} size={13} />
                        <div>{issue.message}</div>
                      </div>
                    ))}
                    {(result.compliance.issues || []).length > 4 && (
                      <span className="field-hint">+{result.compliance.issues.length - 4} more checks in the draft queue.</span>
                    )}
                  </div>
                )}
              </div>
              <div className="card-footer-actions">
                <Button variant="outline" icon="eye" onClick={() => navigate("queue", { focusDraft: result.id })}>
                  Review in queue
                </Button>
                <Button variant="primary" icon="checkCircle" onClick={() => navigate("queue", { focusDraft: result.id })}>
                  Review & approve
                </Button>
              </div>
              <div className="card-foot">Approval is only possible in the Draft Queue, against this exact content hash.</div>
            </div>
          ) : !busy && (
            <div className="card">
              <div className="card-head">
                <div>
                  <h2 className="card-title">Before you generate</h2>
                  <div className="card-sub">A short editorial checklist</div>
                </div>
                <Icon name="bookmark" size={17} style={{ color: "var(--text-mid)" }} />
              </div>
              <div className="card-body">
                <div className="stack-sm">
                  {checklist.map(([title, text], index) => (
                    <div className="row" key={title} style={{ alignItems: "flex-start", gap: 11, paddingBottom: 10, borderBottom: index < checklist.length - 1 ? "1px solid var(--line-soft)" : "none" }}>
                      <span className="mono" style={{ color: "var(--accent)", fontSize: 10, marginTop: 2 }}>0{index + 1}</span>
                      <div>
                        <div style={{ fontSize: 12.5, color: "var(--text-soft)" }}>{title}</div>
                        <p className="field-hint">{text}</p>
                      </div>
                    </div>
                  ))}
                </div>
                <Callout tone="info" title="What Gemini receives" icon="shield">
                  Your project brief, a link policy, the community's recorded rules and post-type constraints, recent draft titles to avoid repeats, and your generation preferences. It never receives your Reddit password.
                </Callout>
              </div>
            </div>
          )}

          {selectedProject && (
            <div className="card">
              <div className="card-head"><div><h2 className="card-title">Project context</h2><div className="card-sub">What the model knows about {selectedProject.name}</div></div></div>
              <div className="card-body">
                <dl className="kv">
                  <dt>Voice</dt><dd>{truncate(selectedProject.brand_voice || "Not recorded", 80)}</dd>
                  <dt>Audience</dt><dd>{truncate(selectedProject.target_audience || "Not recorded", 80)}</dd>
                  <dt>Disclosure</dt><dd>{truncate(selectedProject.disclosure_statement || "Not recorded", 80)}</dd>
                  <dt>Restricted claims</dt><dd>{truncate(selectedProject.restricted_claims || "None recorded", 80)}</dd>
                </dl>
              </div>
              <div className="card-foot">
                Edit these details in <button type="button" className="link-btn" onClick={() => navigate("projects")}>Projects</button>.
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-head">
          <div>
            <h2 className="card-title">Recent drafts</h2>
            <div className="card-sub">Latest additions across the workspace</div>
          </div>
          <Button size="sm" variant="ghost" iconRight="arrowRight" onClick={() => navigate("queue")}>View all</Button>
        </div>
        {recentQuery.loading ? (
          <div className="card-body"><div className="skeleton" style={{ height: 60 }} /></div>
        ) : (recentQuery.data?.items || []).length === 0 ? (
          <EmptyState icon="queue" title="No drafts yet" text="Your first generated draft will appear here and in the Draft Queue." />
        ) : (
          <div className="draft-list">
            {(recentQuery.data.items || []).map((draft) => (
              <button
                type="button"
                className="draft-row"
                key={draft.id}
                onClick={() => navigate("queue", { focusDraft: draft.id })}
              >
                <div className="draft-main">
                  <div className="draft-topline">
                    <StatusBadge status={draft.status} />
                    <span className="mono muted">#{draft.id}</span>
                    <span className="muted" style={{ fontSize: 10.5 }}>r/{draft.subreddit_name}</span>
                  </div>
                  <div className="draft-title truncate">{draft.title}</div>
                  <div className="draft-meta">
                    <span>{draft.project_name}</span>
                    <span className="sep">·</span>
                    <span>{formatDateTime(draft.updated_at)}</span>
                  </div>
                </div>
                <div className="draft-side">
                  <ScoreDots value={draft.promotional_intensity || 0} label={false} />
                  <Icon name="chevronRight" size={14} style={{ color: "var(--muted)" }} />
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
