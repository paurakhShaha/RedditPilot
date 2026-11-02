import React, { useEffect, useMemo, useState } from "react";
import { api, qs } from "../api.js";
import Icon from "../components/Icons.jsx";
import {
  Badge,
  Button,
  Callout,
  ConfirmDialog,
  EmptyState,
  ErrorBlock,
  Field,
  IconButton,
  LoadingBlock,
  Modal,
  PageHead,
  StatusBadge,
  useToast,
} from "../components/ui.jsx";
import { useLoad } from "../hooks.js";
import { MONTHS, formatDate, timeAgo } from "../utils.js";

const PROMOTION_POLICIES = [
  ["unknown", "Unknown"],
  ["allowed_with_disclosure", "Allowed with disclosure"],
  ["restricted", "Restricted"],
  ["prohibited", "Prohibited"],
];

const LINK_POLICIES = [
  ["unknown", "Unknown"],
  ["allowed", "Allowed"],
  ["restricted", "Restricted"],
  ["not_allowed", "Not allowed"],
];

const APPROVAL_OPTIONS = [
  ["review", "Needs review"],
  ["suitable", "Suitable"],
  ["not_recommended", "Not recommended"],
  ["prohibited", "Prohibited"],
];

const POST_TYPES = ["Text post", "Discussion", "Question", "Project showcase", "Tutorial", "Feedback request"];

const EMPTY_FORM = {
  project_id: "",
  name: "",
  description: "",
  self_promotion_policy: "unknown",
  links_policy: "unknown",
  allowed_post_types: [],
  min_account_age_days: "",
  min_karma: "",
  notes: "",
  approval_status: "review",
  rules: [],
};

export default function SubredditManager({ projects, projectId, navigate, refresh }) {
  const toast = useToast();
  const [search, setSearch] = useState("");
  const [modal, setModal] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [verifyTarget, setVerifyTarget] = useState(null);
  const [busyId, setBusyId] = useState(null);

  const query = useLoad(
    () => api.get(`/api/subreddits${qs({ project_id: projectId || undefined })}`),
    [projectId]
  );
  const items = query.data?.items || [];
  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return items;
    return items.filter((item) =>
      `${item.name} ${item.project_name} ${item.notes} ${(item.rules || []).map((rule) => rule.title).join(" ")}`
        .toLowerCase()
        .includes(term)
    );
  }, [items, search]);

  const stats = useMemo(() => ({
    suitable: items.filter((item) => item.approval_status === "suitable").length,
    review: items.filter((item) => item.approval_status === "review").length,
    unverified: items.filter((item) => !item.last_rules_verified_at).length,
    blocked: items.filter((item) => ["prohibited", "not_recommended"].includes(item.approval_status)).length,
  }), [items]);

  const reload = () => { query.reload(); refresh(); };

  const verify = async () => {
    if (!verifyTarget) return;
    setBusyId(verifyTarget.id);
    try {
      await api.post(`/api/subreddits/${verifyTarget.id}/verify`);
      toast.success("Rules verification recorded", `r/${verifyTarget.name} is marked verified as of today.`);
      setVerifyTarget(null);
      reload();
    } catch (error) {
      toast.error("Could not verify rules", error.message);
    } finally {
      setBusyId(null);
    }
  };

  const remove = async () => {
    if (!deleteTarget) return;
    setBusyId(deleteTarget.id);
    try {
      await api.delete(`/api/subreddits/${deleteTarget.id}`);
      toast.success("Community removed", `r/${deleteTarget.name} was removed from the workspace.`);
      setDeleteTarget(null);
      reload();
    } catch (error) {
      toast.error("Community could not be removed", error.message);
    } finally {
      setBusyId(null);
    }
  };

  const activeProjectName = projects.find((project) => String(project.id) === String(projectId))?.name;

  return (
    <div className="page">
      <PageHead
        eyebrow="Subreddit Manager"
        title="Know the room before you speak."
        description="Record each community's self-promotion rules, link policy and verification date. The compliance engine uses these notes — stale or unknown rules raise warnings before publishing."
        actions={(
          <>
            <Badge tone="neutral" dot>{items.length} communities</Badge>
            <Button variant="outline" icon="refresh" onClick={query.reload}>Refresh</Button>
            <Button
              variant="primary"
              icon="plus"
              onClick={() => setModal({ mode: "create", item: null })}
              disabled={!projects.filter((project) => !project.is_archived).length}
            >
              Add community
            </Button>
          </>
        )}
      />

      {!projects.filter((project) => !project.is_archived).length ? (
        <div className="card">
          <EmptyState
            icon="folder"
            title="Create a project first"
            text="Communities belong to a project, because self-promotion context differs by product and audience."
            actions={<Button variant="primary" icon="folder" onClick={() => navigate("projects")}>Create a project</Button>}
          />
        </div>
      ) : (
        <>
          <div className="stat-grid" style={{ marginBottom: 16 }}>
            <div className="stat">
              <span className="stat-label">Suitable</span>
              <span className="stat-value">{stats.suitable}</span>
              <span className="stat-meta sage"><Icon name="checkCircle" size={12} />Reviewed and allowed</span>
            </div>
            <div className="stat">
              <span className="stat-label">Needs review</span>
              <span className="stat-value">{stats.review}</span>
              <span className="stat-meta amber"><Icon name="eye" size={12} />Publishing stays cautious</span>
            </div>
            <div className="stat">
              <span className="stat-label">Rules unverified</span>
              <span className="stat-value">{stats.unverified}</span>
              <span className="stat-meta"><Icon name="clock" size={12} />Mark verified after reading</span>
            </div>
            <div className="stat">
              <span className="stat-label">Off limits</span>
              <span className="stat-value">{stats.blocked}</span>
              <span className="stat-meta red"><Icon name="shield" size={12} />Prohibited or not recommended</span>
            </div>
          </div>

          <div className="row-between" style={{ marginBottom: 14 }}>
            <div className="input-wrap" style={{ maxWidth: 380, width: "100%" }}>
              <span style={{ position: "absolute", left: 11, top: "50%", transform: "translateY(-50%)", color: "var(--muted)", display: "flex" }}>
                <Icon name="search" size={14} />
              </span>
              <input
                className="input"
                style={{ paddingLeft: 34 }}
                placeholder="Search communities or rules…"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </div>
            <span className="field-hint">{activeProjectName || "All projects"} · sorted by name</span>
          </div>

          {query.loading ? (
            <div className="grid grid-2">
              <div className="card"><div className="card-body"><LoadingBlock lines={5} height={24} /></div></div>
              <div className="card"><div className="card-body"><LoadingBlock lines={5} height={24} /></div></div>
            </div>
          ) : query.error ? (
            <div className="card"><ErrorBlock message={query.error} onRetry={query.reload} /></div>
          ) : visible.length === 0 ? (
            <div className="card">
              <EmptyState
                icon="community"
                title={search ? "No communities match that search" : "No communities yet"}
                text={search ? "Try a different phrase or clear the search." : "Add the subreddits you genuinely want to participate in. Read their rules yourself first, then record what you found."}
                actions={!search && (
                  <Button variant="primary" icon="plus" onClick={() => setModal({ mode: "create", item: null })}>Add a community</Button>
                )}
              />
            </div>
          ) : (
            <div className="grid grid-2">
              {visible.map((item) => {
                const verifiedAge = item.rules_verified_age_days;
                const stale = verifiedAge != null && verifiedAge > 90;
                return (
                  <div className="card" key={item.id}>
                    <div className="card-body">
                      <div className="row" style={{ alignItems: "flex-start", gap: 10 }}>
                        <div style={{ minWidth: 0, flex: 1 }}>
                          <div className="row" style={{ gap: 7 }}>
                            <h2 className="card-title" style={{ fontSize: 19 }}>r/{item.name}</h2>
                            <StatusBadge status={item.approval_status} />
                          </div>
                          <div className="card-sub">{item.project_name}{item.description ? ` · ${item.description}` : ""}</div>
                        </div>
                        <div className="row" style={{ gap: 2 }}>
                          <IconButton icon="edit" label="Edit community" size="sm" onClick={() => setModal({ mode: "edit", item })} />
                          <IconButton icon="trash" label="Remove community" size="sm" onClick={() => setDeleteTarget(item)} />
                        </div>
                      </div>

                      <div className="row" style={{ gap: 6, marginTop: 12 }}>
                        <Badge tone={item.self_promotion_policy === "prohibited" ? "red" : item.self_promotion_policy === "allowed_with_disclosure" ? "sage" : "neutral"}>
                          Promotion: {item.self_promotion_policy.replaceAll("_", " ")}
                        </Badge>
                        <Badge tone={item.links_policy === "not_allowed" ? "red" : item.links_policy === "allowed" ? "sage" : "neutral"}>
                          Links: {item.links_policy.replaceAll("_", " ")}
                        </Badge>
                        {item.min_account_age_days != null && <Badge tone="neutral">{item.min_account_age_days}d account</Badge>}
                        {item.min_karma != null && <Badge tone="neutral">{item.min_karma} karma</Badge>}
                      </div>

                      <div className="grid grid-2" style={{ marginTop: 13, gap: 10 }}>
                        <div>
                          <div className="section-label" style={{ marginBottom: 4 }}>Rules verified</div>
                          <div className={`row ${stale || !item.last_rules_verified_at ? "text-red" : "text-sage"}`} style={{ gap: 5, fontSize: 12 }}>
                            <Icon name={item.last_rules_verified_at ? "clock" : "alert"} size={13} />
                            {item.last_rules_verified_at
                              ? `${verifiedAge} day${verifiedAge === 1 ? "" : "s"} ago`
                              : "Never"}
                          </div>
                          <div className="field-hint">{item.last_rules_verified_at ? `Checked ${formatDate(item.last_rules_verified_at)}` : "Review the sidebar before publishing."}</div>
                        </div>
                        <div>
                          <div className="section-label" style={{ marginBottom: 4 }}>Recorded rules</div>
                          <div style={{ fontSize: 12, color: "var(--text-soft)" }}>{(item.rules || []).length} rule{(item.rules || []).length === 1 ? "" : "s"}</div>
                          <div className="field-hint">{(item.allowed_post_types || []).length ? (item.allowed_post_types || []).join(", ") : "No post types restricted"}</div>
                        </div>
                      </div>

                      {(item.rules || []).length > 0 && (
                        <details style={{ marginTop: 12 }}>
                          <summary className="field-hint" style={{ cursor: "pointer" }}>Show recorded rules</summary>
                          <ul className="field-hint" style={{ paddingLeft: 17, marginTop: 6, lineHeight: 1.65 }}>
                            {(item.rules || []).map((rule) => (
                              <li key={rule.id} style={{ marginBottom: 3 }}>
                                <span className="text-soft">{rule.title}</span>{rule.detail ? ` — ${rule.detail}` : ""}
                              </li>
                            ))}
                          </ul>
                        </details>
                      )}

                      {item.notes && <p className="field-hint" style={{ marginTop: 10, borderTop: "1px solid var(--line-soft)", paddingTop: 9 }}>{item.notes}</p>}
                    </div>
                    <div className="card-footer-actions" style={{ justifyContent: "space-between" }}>
                      <span className="field-hint">Added {timeAgo(item.created_at)}</span>
                      <div className="row" style={{ gap: 6 }}>
                        <Button size="sm" variant="outline" icon="checkCircle" onClick={() => setVerifyTarget(item)}>Mark verified</Button>
                        <Button size="sm" variant="ghost" icon="edit" onClick={() => setModal({ mode: "edit", item })}>Edit</Button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}

      {modal && (
        <SubredditModal
          mode={modal.mode}
          item={modal.item}
          projects={projects}
          projectId={projectId}
          onClose={() => setModal(null)}
          onSaved={() => { setModal(null); reload(); }}
        />
      )}

      <ConfirmDialog
        open={!!verifyTarget}
        onClose={() => setVerifyTarget(null)}
        onConfirm={verify}
        tone="sage"
        icon="checkCircle"
        title={`Mark r/${verifyTarget?.name || ""} rules as verified?`}
        message="Only do this after reading the community's current sidebar, wiki and stickied moderation posts yourself. This date is used by the compliance engine to flag stale rules."
        confirmLabel="Yes, rules verified"
        busy={busyId != null}
      />
      <ConfirmDialog
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={remove}
        tone="danger"
        icon="trash"
        title={`Remove r/${deleteTarget?.name || ""}?`}
        message="Communities with drafts, scheduled slots or a weekly plan cannot be deleted. Mark them 'Not recommended' instead to preserve the audit trail."
        confirmLabel="Remove community"
        busy={busyId != null}
      />
    </div>
  );
}

function SubredditModal({ mode, item, projects, projectId, onClose, onSaved }) {
  const toast = useToast();
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [busy, setBusy] = useState(false);

  const availableProjects = projects.filter((project) => !project.is_archived);

  useEffect(() => {
    if (mode === "edit" && item) {
      setForm({
        project_id: String(item.project_id),
        name: item.name,
        description: item.description || "",
        self_promotion_policy: item.self_promotion_policy || "unknown",
        links_policy: item.links_policy || "unknown",
        allowed_post_types: item.allowed_post_types || [],
        min_account_age_days: item.min_account_age_days ?? "",
        min_karma: item.min_karma ?? "",
        notes: item.notes || "",
        approval_status: item.approval_status || "review",
        rules: (item.rules || []).map((rule) => ({ title: rule.title, detail: rule.detail || "" })),
      });
    } else {
      const preferred = availableProjects.find((project) => String(project.id) === String(projectId)) || availableProjects[0];
      setForm({ ...EMPTY_FORM, project_id: preferred ? String(preferred.id) : "" });
    }
  }, [mode, item, projectId, projects]);

  const set = (key, value) => setForm((current) => ({ ...current, [key]: value }));

  const toggleType = (type) => {
    setForm((current) => ({
      ...current,
      allowed_post_types: current.allowed_post_types.includes(type)
        ? current.allowed_post_types.filter((value) => value !== type)
        : [...current.allowed_post_types, type],
    }));
  };

  const addRule = () => setForm((current) => ({ ...current, rules: [...current.rules, { title: "", detail: "" }] }));
  const updateRule = (index, key, value) => setForm((current) => ({
    ...current,
    rules: current.rules.map((rule, ruleIndex) => ruleIndex === index ? { ...rule, [key]: value } : rule),
  }));
  const removeRule = (index) => setForm((current) => ({
    ...current,
    rules: current.rules.filter((_, ruleIndex) => ruleIndex !== index),
  }));

  const submit = async (event) => {
    event.preventDefault();
    if (!form.project_id) return toast.warning("Choose a project", "Communities belong to a project.");
    if (form.name.trim().length < 2) return toast.warning("Add a community name", "For example: webdev, experienced_devs.");
    if (form.self_promotion_policy === "unknown") {
      // A warning is appropriate, but not a hard block: the user may genuinely not know yet.
    }
    const rules = form.rules
      .filter((rule) => rule.title.trim())
      .map((rule, index) => ({ title: rule.title.trim(), detail: rule.detail.trim(), position: index }));
    setBusy(true);
    try {
      const payload = {
        name: form.name.trim(),
        description: form.description,
        self_promotion_policy: form.self_promotion_policy,
        links_policy: form.links_policy,
        allowed_post_types: form.allowed_post_types,
        min_account_age_days: form.min_account_age_days === "" ? null : Number(form.min_account_age_days),
        min_karma: form.min_karma === "" ? null : Number(form.min_karma),
        notes: form.notes,
        approval_status: form.approval_status,
        rules,
      };
      if (mode === "edit") {
        await api.patch(`/api/subreddits/${item.id}`, payload);
        toast.success("Community updated", `r/${form.name} was saved.`);
      } else {
        await api.post("/api/subreddits", { ...payload, project_id: Number(form.project_id) });
        toast.success("Community added", `r/${form.name} is now part of the workspace.`);
      }
      onSaved();
    } catch (error) {
      toast.error("Could not save community", error.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      title={mode === "edit" ? `Edit r/${item?.name}` : "Add a community"}
      subtitle="Record what the rules actually say — the compliance engine fails closed on unknown policies."
      size="lg"
      busy={busy}
      footer={(
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button variant="primary" icon="check" onClick={submit} loading={busy}>
            {mode === "edit" ? "Save community" : "Add community"}
          </Button>
        </>
      )}
    >
      <form onSubmit={submit}>
        <div className="stack">
          <div className="form-grid">
            <Field label="Project">
              <select className="select" value={form.project_id} onChange={(event) => set("project_id", event.target.value)} disabled={mode === "edit"}>
                <option value="" disabled>Select a project</option>
                {availableProjects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
              </select>
            </Field>
            <Field label="Community name" hint="Without r/ — for example, webdev.">
              <input className="input" value={form.name} onChange={(event) => set("name", event.target.value)} placeholder="webdev" />
            </Field>
            <Field label="What is this community for?" optional className="full">
              <input className="input" value={form.description} onChange={(event) => set("description", event.target.value)} placeholder="A short description in your own words" />
            </Field>
          </div>

          <hr className="divider" />

          <div className="form-grid">
            <Field label="Self-promotion policy" hint="Choose Unknown until you have read the rules.">
              <select className="select" value={form.self_promotion_policy} onChange={(event) => set("self_promotion_policy", event.target.value)}>
                {PROMOTION_POLICIES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </Field>
            <Field label="Links policy">
              <select className="select" value={form.links_policy} onChange={(event) => set("links_policy", event.target.value)}>
                {LINK_POLICIES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </Field>
            <Field label="Minimum account age (days)" optional>
              <input className="input" type="number" min="0" max="36500" value={form.min_account_age_days} onChange={(event) => set("min_account_age_days", event.target.value)} placeholder="e.g. 30" />
            </Field>
            <Field label="Minimum karma" optional>
              <input className="input" type="number" min="0" value={form.min_karma} onChange={(event) => set("min_karma", event.target.value)} placeholder="e.g. 100" />
            </Field>
            <Field label="Your assessment" className="full" hint="Mark 'Suitable' only after personally checking the current rules.">
              <select className="select" value={form.approval_status} onChange={(event) => set("approval_status", event.target.value)}>
                {APPROVAL_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </Field>
          </div>

          <Field label="Allowed post types" hint="Leave empty if the community does not restrict post types.">
            <div className="post-type-grid">
              {POST_TYPES.map((type) => (
                <button
                  type="button"
                  key={type}
                  className={`type-chip ${form.allowed_post_types.includes(type) ? "on" : ""}`}
                  onClick={() => toggleType(type)}
                >
                  {type}
                </button>
              ))}
            </div>
          </Field>

          <div>
            <div className="row-between" style={{ marginBottom: 8 }}>
              <div>
                <div className="section-label">Recorded rules</div>
                <div className="field-hint">Copy the substance of the rules, not the whole sidebar.</div>
              </div>
              <Button size="sm" variant="outline" icon="plus" onClick={addRule}>Add rule</Button>
            </div>
            {form.rules.length === 0 ? (
              <div className="callout warning">
                <Icon name="alert" size={15} />
                <div>No rules recorded. The compliance engine will warn that rules are unverified, and publishing may be blocked if the verification date is stale.</div>
              </div>
            ) : (
              <div className="rules-editor">
                {form.rules.map((rule, index) => (
                  <div className="rule-row" key={index}>
                    <input className="input" value={rule.title} placeholder="Rule title" onChange={(event) => updateRule(index, "title", event.target.value)} />
                    <textarea className="textarea rule-detail" rows={1} value={rule.detail} placeholder="Detail or your note" onChange={(event) => updateRule(index, "detail", event.target.value)} />
                    <IconButton icon="trash" label="Remove rule" size="sm" onClick={() => removeRule(index)} />
                  </div>
                ))}
              </div>
            )}
          </div>

          <Field label="Notes" optional hint="Flair requirements, weekly threads, moderator preferences, anything you learned.">
            <textarea className="textarea" rows={3} value={form.notes} onChange={(event) => set("notes", event.target.value)} placeholder="e.g. Use the Showcase flair. No launch posts on weekends." />
          </Field>

          <Callout tone="info" icon="info">
            After saving, use <strong>Mark verified</strong> once you have read the live rules. Verification older than 90 days warns; older than 180 days blocks publishing.
          </Callout>
        </div>
      </form>
    </Modal>
  );
}
