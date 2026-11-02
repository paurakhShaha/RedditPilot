import React, { useEffect, useMemo, useState } from "react";
import { api, qs } from "../api.js";
import Icon from "../components/Icons.jsx";
import {
  Badge,
  Button,
  Callout,
  CheckRow,
  ConfirmDialog,
  CopyButton,
  EmptyState,
  ErrorBlock,
  Field,
  LoadingBlock,
  Meter,
  Modal,
  PageHead,
  ScoreDots,
  StatusBadge,
  useToast,
} from "../components/ui.jsx";
import { useLoad } from "../hooks.js";
import { formatDate, formatDateTime, formatNumber, truncate } from "../utils.js";

const FILTERS = [
  ["all", "All"],
  ["Pending Review", "Pending"],
  ["Approved", "Approved"],
  ["Scheduled", "Scheduled"],
  ["Rejected", "Rejected"],
  ["Published", "Published"],
  ["Failed", "Failed"],
  ["Archived", "Archived"],
];

function blockerCount(draft) {
  return draft.compliance?.blockers ?? (draft.rule_violations || []).length;
}

function warningCount(draft) {
  return draft.compliance?.warnings ?? (draft.warnings || []).length;
}

export default function DraftQueue({ projects, projectId, settings, refresh, focusDraft, setFocusDraft, navigate }) {
  const toast = useToast();
  const [status, setStatus] = useState("all");
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [selectedId, setSelectedId] = useState(null);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(search.trim()), 280);
    return () => clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    if (focusDraft) {
      setSelectedId(focusDraft);
      setFocusDraft(null);
    }
  }, [focusDraft, setFocusDraft]);

  const query = useLoad(
    () => api.get(`/api/drafts${qs({ status, project_id: projectId || undefined, search: debounced || undefined, limit: 200 })}`),
    [status, projectId, debounced]
  );

  const items = query.data?.items || [];
  const counts = query.data?.status_counts || {};
  const total = query.data?.total || 0;

  const closeDetail = () => {
    setSelectedId(null);
    query.reload();
  };

  return (
    <div className="page">
      <PageHead
        eyebrow="Draft Queue"
        title="Nothing moves without you."
        description="Review the exact words, resolve compliance blockers, and approve one version at a time. Editing an approved draft invalidates its approval."
        actions={(
          <>
            <Badge tone="neutral" dot>{total} in queue</Badge>
            <Button variant="outline" icon="refresh" onClick={query.reload}>Refresh</Button>
            <Button variant="primary" icon="sparkles" onClick={() => navigate("studio")}>Generate draft</Button>
          </>
        )}
      />

      <div className="card flush">
        <div style={{ padding: "0 16px" }}>
          <div className="tabs" role="tablist" aria-label="Filter drafts by status">
            {FILTERS.map(([value, label]) => (
              <button
                key={value}
                type="button"
                role="tab"
                aria-selected={status === value}
                className={`tab ${status === value ? "active" : ""}`}
                onClick={() => setStatus(value)}
              >
                {label}
                <span className="count">{value === "all" ? Object.values(counts).reduce((sum, count) => sum + count, 0) : (counts[value] || 0)}</span>
              </button>
            ))}
          </div>
          <div className="row-between" style={{ padding: "13px 0" }}>
            <div className="input-wrap" style={{ maxWidth: 380, width: "100%" }}>
              <span style={{ position: "absolute", left: 11, top: "50%", transform: "translateY(-50%)", color: "var(--muted)", display: "flex" }}>
                <Icon name="search" size={14} />
              </span>
              <input
                className="input"
                style={{ paddingLeft: 34 }}
                placeholder="Search titles and body copy…"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                aria-label="Search drafts"
              />
            </div>
            <span className="field-hint">
              {projectId ? projects.find((project) => String(project.id) === String(projectId))?.name : "All projects"}
              {" · "}{items.length} shown
            </span>
          </div>
        </div>

        {query.loading ? (
          <div style={{ padding: 20 }}><LoadingBlock lines={5} height={38} /></div>
        ) : query.error ? (
          <ErrorBlock message={query.error} onRetry={query.reload} />
        ) : items.length === 0 ? (
          <EmptyState
            icon="queue"
            title={debounced ? "No drafts match that search" : "The queue is clear"}
            text={debounced ? "Try a broader phrase or clear the status filter." : "Generate a draft in the Content Studio. It will arrive here as Pending Review and wait for your decision."}
            actions={!debounced && (
              <Button variant="primary" icon="studio" onClick={() => navigate("studio")}>Open Content Studio</Button>
            )}
          />
        ) : (
          <div className="draft-list">
            {items.map((draft) => (
              <button
                type="button"
                key={draft.id}
                className={`draft-row ${selectedId === draft.id ? "selected" : ""}`}
                onClick={() => setSelectedId(draft.id)}
              >
                <div className="draft-main">
                  <div className="draft-topline">
                    <StatusBadge status={draft.status} />
                    <span className="mono muted">#{draft.id}</span>
                    {draft.is_approved && <Badge tone="sage">Approved version</Badge>}
                    {draft.scheduled_slot && <Badge tone="blue" dot>Scheduled {formatDate(draft.scheduled_slot.slot_start)}</Badge>}
                    {draft.published_post && <Badge tone="sage">Published</Badge>}
                  </div>
                  <div className="draft-title truncate">{draft.title}</div>
                  <div className="draft-meta">
                    <span>r/{draft.subreddit_name}</span>
                    <span className="sep">·</span>
                    <span>{draft.project_name}</span>
                    <span className="sep">·</span>
                    <span>{draft.objective}</span>
                    <span className="sep">·</span>
                    <span>v{draft.version}</span>
                    <span className="sep">·</span>
                    <span>edited {formatDateTime(draft.updated_at)}</span>
                  </div>
                  <p className="draft-excerpt line-2">{truncate((draft.body || "").replace(/\s+/g, " "), 220)}</p>
                </div>
                <div className="draft-side">
                  <ScoreDots value={draft.promotional_intensity || 0} label={false} />
                  <div className="row" style={{ gap: 5 }}>
                    {blockerCount(draft) > 0 && <Badge tone="red">{blockerCount(draft)} blockers</Badge>}
                    {blockerCount(draft) === 0 && warningCount(draft) > 0 && <Badge tone="amber">{warningCount(draft)} notes</Badge>}
                    {blockerCount(draft) === 0 && warningCount(draft) === 0 && <Badge tone="sage">Clear</Badge>}
                  </div>
                  <Icon name="chevronRight" size={14} style={{ color: "var(--muted)" }} />
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {selectedId && (
        <DraftDetail
          draftId={selectedId}
          settings={settings}
          onClose={closeDetail}
          onChanged={() => { query.reload(); refresh(); }}
          onCreated={(id) => { setSelectedId(id); query.reload(); refresh(); }}
          projects={projects}
          navigate={navigate}
        />
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ detail */
function DraftDetail({ draftId, onClose, onChanged, onCreated, settings, projects, navigate }) {
  const toast = useToast();
  const detail = useLoad(() => api.get(`/api/drafts/${draftId}`), [draftId]);
  const check = useLoad(() => api.get(`/api/drafts/${draftId}/publish/check`), [draftId]);
  const draft = detail.data;
  const [form, setForm] = useState({ title: "", body: "", disclosure: "", link_url: "", change_note: "" });
  const [saving, setSaving] = useState(false);
  const [dialog, setDialog] = useState(null);
  const [confirmClose, setConfirmClose] = useState(false);
  const [regenerating, setRegenerating] = useState(false);

  useEffect(() => {
    if (!draft) return;
    setForm({
      title: draft.title || "",
      body: draft.body || "",
      disclosure: draft.disclosure || "",
      link_url: draft.link_url || "",
      change_note: "",
    });
  }, [draft?.id, draft?.version, draft?.updated_at]);

  const dirty = useMemo(() => {
    if (!draft) return false;
    return (
      form.title !== (draft.title || "")
      || form.body !== (draft.body || "")
      || form.disclosure !== (draft.disclosure || "")
      || form.link_url !== (draft.link_url || "")
    );
  }, [form, draft]);

  const refreshAll = () => {
    detail.reload();
    check.reload();
    onChanged();
  };

  const requestClose = () => {
    if (dirty) setConfirmClose(true);
    else onClose();
  };

  const save = async () => {
    if (!draft) return;
    setSaving(true);
    const wasApproved = draft.is_approved;
    try {
      await api.patch(`/api/drafts/${draft.id}`, {
        title: form.title,
        body: form.body,
        disclosure: form.disclosure,
        link_url: form.link_url || null,
        change_note: form.change_note || "Manual edit",
      });
      toast.success("Draft saved", wasApproved ? "Content changed, so the previous approval was invalidated. Review and approve again." : "Compliance checks refreshed for this version.");
      refreshAll();
    } catch (error) {
      toast.error("Could not save draft", error.message);
    } finally {
      setSaving(false);
    }
  };

  const regenerate = async () => {
    setRegenerating(true);
    try {
      await api.post(`/api/drafts/${draftId}/regenerate`);
      toast.success("Draft regenerated", "A fresh version is waiting for review. Any previous approval is invalid.");
      setDialog(null);
      refreshAll();
    } catch (error) {
      toast.error("Regeneration failed", error.message);
    } finally {
      setRegenerating(false);
    }
  };

  const changeStatus = async (action, message) => {
    try {
      await api.post(`/api/drafts/${draftId}/${action}`);
      toast.success(message, "");
      setDialog(null);
      refreshAll();
    } catch (error) {
      toast.error("Action failed", error.message);
    }
  };

  const remove = async () => {
    try {
      await api.delete(`/api/drafts/${draftId}`);
      toast.success("Draft deleted", "The audit entry remains in the workspace journal.");
      onClose();
    } catch (error) {
      toast.error("Could not delete draft", error.message);
    }
  };

  const openManual = async () => {
    setDialog("manual-loading");
    try {
      const prepared = await api.post(`/api/drafts/${draftId}/publish/manual/prepare`);
      setDialog({ type: "manual", prepared });
    } catch (error) {
      toast.error("Manual publishing is blocked", error.message);
      setDialog(null);
    }
  };

  if (detail.loading) {
    return (
      <Modal open onClose={requestClose} title={`Draft #${draftId}`} size="lg">
        <LoadingBlock lines={6} height={22} />
      </Modal>
    );
  }

  if (detail.error || !draft) {
    return (
      <Modal open onClose={onClose} title={`Draft #${draftId}`} size="lg" footer={<Button onClick={onClose}>Close</Button>}>
        <ErrorBlock message={detail.error || "Draft not found."} onRetry={detail.reload} />
      </Modal>
    );
  }

  const compliance = draft.compliance || {};
  const issues = compliance.issues || [];
  const blockers = issues.filter((issue) => issue.severity === "blocker");
  const warnings = issues.filter((issue) => issue.severity === "warning");
  const info = issues.filter((issue) => issue.severity === "info");
  const canApprove = !["Published", "Archived", "Approved"].includes(draft.status) && !draft.published_post;
  const canPublish = check.data?.is_approved && (check.data?.compliance?.blockers || 0) === 0;
  const isPublished = draft.status === "Published" || !!draft.published_post;
  const canEdit = !isPublished && !draft.published_post;

  return (
    <>
      <Modal
        open
        onClose={requestClose}
        size="lg"
        title={(
          <span className="row" style={{ gap: 9 }}>
            <span>Draft #{draft.id}</span>
            <StatusBadge status={draft.status} />
          </span>
        )}
        subtitle={`r/${draft.subreddit_name} · ${draft.project_name} · version ${draft.version} · ${draft.post_type}`}
        footer={(
          <>
            <span className="foot-note">
              {dirty ? "Unsaved edits. Saving a changed approved draft invalidates its approval." : "Approval applies only to this exact content version."}
            </span>
            <Button variant="ghost" onClick={requestClose}>Close</Button>
            <Button variant="outline" icon="save" onClick={save} disabled={!dirty || saving || !canEdit} loading={saving}>
              Save changes
            </Button>
            {canApprove && (
              <Button variant="primary" icon="checkCircle" onClick={() => setDialog("approve")} disabled={blockers.length > 0}>
                Approve
              </Button>
            )}
          </>
        )}
      >
        <div className="detail-grid">
          <div className="detail-main">
            <div className="detail-section">
              <div className="detail-section-head">
                <div>
                  <div className="section-label">The post</div>
                  <div className="field-hint">Edit freely. Every save creates a revision.</div>
                </div>
                {dirty && <Badge tone="amber">Unsaved</Badge>}
              </div>

              <div className="stack-sm">
                <Field label="Title" hint={`${form.title.length}/300`}>
                  <input
                    className="input"
                    value={form.title}
                    maxLength={300}
                    onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))}
                    disabled={!canEdit}
                  />
                </Field>
                <Field label="Body" hint={`${form.body.length} characters · Reddit self-posts allow 40,000`}>
                  <textarea
                    className="textarea editor-body"
                    value={form.body}
                    onChange={(event) => setForm((current) => ({ ...current, body: event.target.value }))}
                    disabled={!canEdit}
                  />
                </Field>
                <Field label="Disclosure" hint="Appended to the body at publish time if not already present.">
                  <textarea
                    className="textarea"
                    rows={2}
                    value={form.disclosure}
                    onChange={(event) => setForm((current) => ({ ...current, disclosure: event.target.value }))}
                    disabled={!canEdit}
                  />
                </Field>
                <div className="form-grid">
                  <Field label="Project link" optional hint="Leave empty for a link-free post.">
                    <input
                      className="input"
                      value={form.link_url}
                      placeholder="https://…"
                      onChange={(event) => setForm((current) => ({ ...current, link_url: event.target.value }))}
                      disabled={!canEdit}
                    />
                  </Field>
                  <Field label="Change note" optional hint="Recorded in revision history.">
                    <input
                      className="input"
                      value={form.change_note}
                      maxLength={300}
                      placeholder="e.g. Tightened the opening"
                      onChange={(event) => setForm((current) => ({ ...current, change_note: event.target.value }))}
                      disabled={!canEdit}
                    />
                  </Field>
                </div>
              </div>

              {draft.is_approved && dirty && (
                <Callout tone="warning" title="Your approval will be invalidated" icon="shield">
                  This draft is approved for its current content hash. Saving these edits returns it to Pending Review and requires a new human approval.
                </Callout>
              )}

              {draft.last_error && (
                <Callout tone="danger" title="Last error" icon="alertCircle">{draft.last_error}</Callout>
              )}

              <div className="row" style={{ marginTop: 14 }}>
                <Button variant="outline" size="sm" icon="refresh" onClick={() => setDialog("regenerate")} disabled={!canEdit || regenerating}>
                  Regenerate with Gemini
                </Button>
                <Button variant="ghost" size="sm" icon="copy" onClick={() => setDialog("duplicate")} disabled={isPublished}>
                  Duplicate for another community
                </Button>
                <div className="spacer" />
                {draft.status === "Archived" ? (
                  <Button variant="ghost" size="sm" icon="restore" onClick={() => changeStatus("restore", "Draft restored to Pending Review")}>Restore</Button>
                ) : (
                  <Button variant="ghost" size="sm" icon="archive" onClick={() => setDialog("archive")} disabled={isPublished}>Archive</Button>
                )}
                <Button variant="ghost" size="sm" icon="trash" onClick={() => setDialog("delete")} disabled={!!draft.published_post}>Delete</Button>
              </div>
            </div>

            <div className="detail-section">
              <div className="detail-section-head">
                <div>
                  <div className="section-label">Provenance</div>
                  <div className="field-hint">Why the model wrote it this way</div>
                </div>
              </div>
              <div className="card" style={{ background: "rgba(0,0,0,.16)", padding: "13px 14px" }}>
                <dl className="kv" style={{ gridTemplateColumns: "110px 1fr" }}>
                  <dt>Objective</dt><dd>{draft.objective || "—"}</dd>
                  <dt>Topic</dt><dd style={{ textAlign: "left" }}>{draft.topic || "—"}</dd>
                  <dt>Relevance</dt><dd style={{ textAlign: "left" }}>{draft.relevance || "Not supplied"}</dd>
                  <dt>Model</dt><dd><span className="mono">{draft.model || "Manual / unknown"}</span></dd>
                  <dt>Source</dt><dd>{draft.source}</dd>
                  <dt>Content hash</dt><dd><span className="mono">{draft.content_hash?.slice(0, 16)}…</span></dd>
                  <dt>Created</dt><dd>{formatDateTime(draft.created_at)}</dd>
                  <dt>Updated</dt><dd>{formatDateTime(draft.updated_at)}</dd>
                </dl>
              </div>
            </div>

            <div className="detail-section">
              <div className="detail-section-head">
                <div>
                  <div className="section-label">Revision history</div>
                  <div className="field-hint">{draft.revision_count || 0} saved revision{(draft.revision_count || 0) === 1 ? "" : "s"}</div>
                </div>
              </div>
              {(draft.approved_revisions || []).length === 0 ? (
                <p className="field-hint">No revisions recorded.</p>
              ) : (
                <div className="stack-sm">
                  {draft.approved_revisions.slice(0, 5).map((revision) => (
                    <div key={revision.id} className="row" style={{ alignItems: "flex-start", gap: 9, fontSize: 11.5 }}>
                      <span className="badge badge-neutral">v{revision.version}</span>
                      <div style={{ minWidth: 0 }}>
                        <div className="text-soft truncate" style={{ maxWidth: 460 }}>{revision.title}</div>
                        <div className="muted">{revision.change_note || "Edit"} · {formatDateTime(revision.created_at)}</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="detail-side">
            <div className="detail-section">
              <div className="detail-section-head">
                <div className="section-label">Human decision</div>
                <ScoreDots value={draft.promotional_intensity || 0} />
              </div>
              {draft.is_approved ? (
                <Callout tone="success" title="Approved for this exact version" icon="checkCircle">
                  Approved {formatDateTime(draft.approval?.approved_at)}. Editing the content invalidates this approval.
                </Callout>
              ) : draft.status === "Approved" ? (
                <Callout tone="warning" title="Approval is stale" icon="alert">The content changed after approval. Review and approve again.</Callout>
              ) : (
                <p className="field-hint">
                  {draft.status === "Rejected" ? "This draft was rejected. You may edit and re-submit it for review." : "This draft has no valid approval. Publishing is blocked until you approve it."}
                </p>
              )}
              <div className="row" style={{ marginTop: 11 }}>
                {canApprove && (
                  <Button
                    variant="primary"
                    size="sm"
                    icon="checkCircle"
                    onClick={() => setDialog("approve")}
                    disabled={blockers.length > 0}
                    title={blockers.length ? "Resolve compliance blockers first" : "Approve this exact version"}
                  >
                    Review & approve
                  </Button>
                )}
                {!isPublished && (
                  <Button variant="ghost" size="sm" icon="xCircle" onClick={() => setDialog("reject")}>Reject</Button>
                )}
              </div>
              {blockers.length > 0 && (
                <p className="field-hint" style={{ color: "var(--red)", marginTop: 6 }}>
                  {blockers.length} compliance blocker{blockers.length === 1 ? "" : "s"} must be resolved before approval.
                </p>
              )}
            </div>

            <div className="detail-section">
              <div className="detail-section-head">
                <div className="section-label">Publishing</div>
                <Badge tone={settings?.publishing_mode === "api" ? "blue" : "neutral"}>
                  {settings?.publishing_mode === "api" ? "API mode" : "Manual mode"}
                </Badge>
              </div>
              {isPublished ? (
                <Callout tone="success" title="This draft is published" icon="send">
                  {draft.published_post?.url ? (
                    <a href={draft.published_post.url} target="_blank" rel="noreferrer">Open the Reddit post <Icon name="external" size={11} /></a>
                  ) : "A publication record exists for this draft."}
                </Callout>
              ) : (
                <>
                  <p className="field-hint" style={{ marginBottom: 9 }}>
                    Publishing requires a valid approval and zero compliance blockers. RedditPilot never publishes on its own.
                  </p>
                  <div className="stack-sm">
                    <Button
                      variant="outline"
                      icon="copy"
                      block
                      onClick={openManual}
                      loading={dialog === "manual-loading"}
                      disabled={!canPublish}
                    >
                      Publish manually
                    </Button>
                    <Button
                      variant={check.data?.api_eligible ? "primary" : "outline"}
                      icon="send"
                      block
                      onClick={() => setDialog("api")}
                      disabled={!check.data?.api_eligible}
                    >
                      Publish via Reddit API
                    </Button>
                  </div>
                  {!canPublish && (
                    <p className="field-hint" style={{ marginTop: 7 }}>
                      {!check.data?.is_approved ? "Approve this version first." : "Resolve publish-stage compliance blockers first."}
                    </p>
                  )}
                  {check.data && !check.data.api_eligible && check.data.api_blockers?.length > 0 && (
                    <details style={{ marginTop: 9 }}>
                      <summary className="field-hint" style={{ cursor: "pointer" }}>Why API publishing is unavailable</summary>
                      <ul className="field-hint" style={{ paddingLeft: 17, marginTop: 5 }}>
                        {check.data.api_blockers.slice(0, 7).map((reason) => <li key={reason} style={{ marginBottom: 3 }}>{reason}</li>)}
                      </ul>
                    </details>
                  )}
                  {draft.scheduled_slot && (
                    <p className="field-hint" style={{ marginTop: 8 }}>
                      Linked slot: {formatDateTime(draft.scheduled_slot.slot_start)} ({draft.scheduled_slot.status})
                    </p>
                  )}
                </>
              )}
            </div>

            <div className="detail-section">
              <div className="detail-section-head">
                <div className="section-label">Compliance report</div>
                <Badge tone={blockers.length ? "red" : warnings.length ? "amber" : "sage"}>
                  {blockers.length ? `${blockers.length} blockers` : warnings.length ? `${warnings.length} warnings` : "Clear"}
                </Badge>
              </div>
              <div className="meter-row">
                <span>Promotional intensity</span>
                <span>{compliance.promotional_score ?? draft.promotional_intensity ?? 0}/5 · limit {settings?.max_promo_score ?? 3}</span>
              </div>
              <Meter value={compliance.promotional_score ?? draft.promotional_intensity ?? 0} max={5} tone={(compliance.promotional_score ?? 0) > (settings?.max_promo_score ?? 3) ? "var(--red)" : undefined} />
              <div className="issue-list" style={{ marginTop: 11 }}>
                {issues.length === 0 && <p className="field-hint">No compliance issues recorded.</p>}
                {issues.map((issue) => (
                  <div key={`${issue.code}-${issue.message}`} className={`issue ${issue.severity}`}>
                    <Icon name={issue.severity === "blocker" ? "alertCircle" : issue.severity === "warning" ? "alert" : "info"} size={13} />
                    <div>{issue.message}<span className="issue-code">{issue.code}</span></div>
                  </div>
                ))}
              </div>
              {compliance.weekly && (
                <p className="field-hint" style={{ marginTop: 8 }}>
                  Weekly usage: {compliance.weekly.published_last_7_days}/{compliance.weekly.limit} published in the last 7 days.
                </p>
              )}
              {compliance.duplicates?.similar_body?.length > 0 && (
                <p className="field-hint" style={{ marginTop: 4 }}>
                  Closest existing draft: #{compliance.duplicates.similar_body[0].draft_id} at {compliance.duplicates.similar_body[0].similarity}% similarity.
                </p>
              )}
              {compliance.rules_verified_age_days != null && (
                <p className="field-hint" style={{ marginTop: 4 }}>
                  Community rules verified {compliance.rules_verified_age_days} days ago.
                </p>
              )}
            </div>

            {(draft.approval_history || []).length > 0 && (
              <div className="detail-section">
                <div className="detail-section-head"><div className="section-label">Approval history</div></div>
                <div className="stack-sm">
                  {draft.approval_history.map((approval) => (
                    <div key={approval.id} style={{ fontSize: 11 }}>
                      <div className="row" style={{ gap: 6 }}>
                        <Badge tone={approval.is_valid ? "sage" : "neutral"}>{approval.is_valid ? "Valid" : "Invalidated"}</Badge>
                        <span className="muted">{formatDateTime(approval.approved_at)}</span>
                      </div>
                      {approval.invalidation_reason && <p className="field-hint" style={{ marginTop: 2 }}>{approval.invalidation_reason}</p>}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </Modal>

      <ApproveDialog
        open={dialog === "approve"}
        onClose={() => setDialog(null)}
        draft={draft}
        onApproved={() => {
          setDialog(null);
          toast.success("Draft approved", "Approval recorded for this exact content version.");
          refreshAll();
        }}
      />
      <RejectDialog
        open={dialog === "reject"}
        onClose={() => setDialog(null)}
        draft={draft}
        onRejected={() => {
          setDialog(null);
          toast.warning("Draft rejected", "The draft was removed from the publishable queue.");
          refreshAll();
        }}
      />
      <DuplicateDialog
        open={dialog === "duplicate"}
        onClose={() => setDialog(null)}
        draft={draft}
        onCreated={(id) => {
          setDialog(null);
          toast.success("New draft created", "A fresh draft for the new community is waiting for review.");
          onCreated(id);
        }}
      />
      <ConfirmDialog
        open={dialog === "regenerate"}
        onClose={() => setDialog(null)}
        onConfirm={regenerate}
        busy={regenerating}
        tone="primary"
        icon="sparkles"
        title="Regenerate this draft?"
        message="Gemini will replace the title, body and disclosure with a materially different version. The current approval, if any, will be invalidated. This cannot be undone, though revisions are kept."
        confirmLabel="Regenerate"
      />
      <ConfirmDialog
        open={dialog === "archive"}
        onClose={() => setDialog(null)}
        onConfirm={() => changeStatus("archive", "Draft archived")}
        tone="danger"
        icon="archive"
        title="Archive this draft?"
        message="The draft leaves the active queue and any approval is invalidated. You can restore it later."
        confirmLabel="Archive draft"
      />
      <ConfirmDialog
        open={dialog === "delete"}
        onClose={() => setDialog(null)}
        onConfirm={remove}
        tone="danger"
        icon="trash"
        title="Delete this draft?"
        message="This permanently deletes the draft and its revisions. Publication history is unaffected. Drafts with a publication record cannot be deleted."
        confirmLabel="Delete permanently"
      />
      <ConfirmDialog
        open={confirmClose}
        onClose={() => setConfirmClose(false)}
        onConfirm={() => { setConfirmClose(false); onClose(); }}
        tone="primary"
        icon="edit"
        title="Discard unsaved changes?"
        message="Your edits to the title, body, disclosure or link have not been saved."
        confirmLabel="Discard edits"
        cancelLabel="Keep editing"
      />

      {dialog?.type === "manual" && (
        <ManualPublishDialog
          draft={draft}
          prepared={dialog.prepared}
          onClose={() => setDialog(null)}
          onPublished={() => {
            setDialog(null);
            toast.success("Publication recorded", "The Reddit URL is stored. Metrics can be added in Published Posts.");
            refreshAll();
          }}
        />
      )}

      {dialog === "api" && (
        <ApiPublishDialog
          draft={draft}
          check={check.data}
          onClose={() => setDialog(null)}
          onPublished={(result) => {
            setDialog(null);
            if (result.warning) toast.warning("Submission result uncertain", result.warning);
            else toast.success("Published via API", result.message);
            refreshAll();
          }}
        />
      )}
    </>
  );
}

/* ------------------------------------------------------------------ dialogs */
function ApproveDialog({ open, onClose, draft, onApproved }) {
  const toast = useToast();
  const [attested, setAttested] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) { setAttested(false); setNote(""); }
  }, [open]);

  const submit = async () => {
    setBusy(true);
    try {
      await api.post(`/api/drafts/${draft.id}/approve`, { attested, note: note.trim() });
      onApproved();
    } catch (error) {
      toast.error("Approval blocked", error.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Approve this exact version"
      subtitle={`Draft #${draft.id} · v${draft.version} · r/${draft.subreddit_name}`}
      size="sm"
      busy={busy}
      footer={(
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button variant="primary" icon="checkCircle" onClick={submit} loading={busy} disabled={!attested}>Record approval</Button>
        </>
      )}
    >
      <div className="stack">
        <div className="card" style={{ background: "rgba(0,0,0,.18)", padding: "12px 13px" }}>
          <div className="section-label" style={{ marginBottom: 4 }}>Content to be approved</div>
          <div className="serif" style={{ fontSize: 15, lineHeight: 1.4 }}>{draft.title}</div>
          <div className="mono muted" style={{ marginTop: 5 }}>hash {draft.content_hash?.slice(0, 20)}…</div>
        </div>
        <CheckRow checked={attested} onChange={setAttested}>
          I have read this exact title, body, disclosure and link, checked the community's current rules, and confirm it is appropriate to post from my account.
        </CheckRow>
        <Field label="Approval note" optional>
          <input className="input" value={note} maxLength={500} onChange={(event) => setNote(event.target.value)} placeholder="e.g. Checked r/webdev rules and flair" />
        </Field>
        <Callout tone="info" icon="shield">
          This approval is tied to the content hash. Any later edit invalidates it automatically.
        </Callout>
      </div>
    </Modal>
  );
}

function RejectDialog({ open, onClose, draft, onRejected }) {
  const toast = useToast();
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { if (open) setReason(""); }, [open]);

  const submit = async () => {
    if (reason.trim().length < 2) return toast.warning("Add a reason", "Record why this draft is being rejected.");
    setBusy(true);
    try {
      await api.post(`/api/drafts/${draft.id}/reject`, { reason: reason.trim() });
      onRejected();
    } catch (error) {
      toast.error("Could not reject draft", error.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Reject this draft"
      subtitle={`Draft #${draft.id} · r/${draft.subreddit_name}`}
      size="sm"
      busy={busy}
      footer={(
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button variant="danger" icon="xCircle" onClick={submit} loading={busy}>Reject draft</Button>
        </>
      )}
    >
      <div className="stack">
        <p className="field-hint">Rejection invalidates any approval and removes the draft from the publishable queue. You can edit and approve it later.</p>
        <Field label="Reason" hint="Keep it specific; this is recorded in the audit log.">
          <textarea className="textarea" rows={3} value={reason} maxLength={500} onChange={(event) => setReason(event.target.value)} placeholder="e.g. Too promotional for this community's rules" />
        </Field>
      </div>
    </Modal>
  );
}

function DuplicateDialog({ open, onClose, draft, onCreated }) {
  const toast = useToast();
  const communities = useLoad(() => api.get(`/api/subreddits?project_id=${draft.project_id}`), [draft.project_id]);
  const [subredditId, setSubredditId] = useState("");
  const [topic, setTopic] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setTopic(draft.topic || "");
    setNotes("");
    setBusy(false);
    const available = (communities.data?.items || []).filter((row) => row.id !== draft.subreddit_id);
    setSubredditId(available[0] ? String(available[0].id) : "");
  }, [open, draft.topic, draft.subreddit_id, communities.data]);

  const submit = async () => {
    if (!subredditId) return toast.warning("Choose a community", "Add another subreddit to this project first.");
    setBusy(true);
    try {
      const created = await api.post(`/api/drafts/${draft.id}/duplicate`, {
        subreddit_id: Number(subredditId),
        topic: topic.trim() || null,
        additional_notes: notes.trim(),
      });
      onCreated(created.id);
    } catch (error) {
      toast.error("Could not create a new draft", error.message);
    } finally {
      setBusy(false);
    }
  };

  const options = (communities.data?.items || []).filter((row) => row.id !== draft.subreddit_id);

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Duplicate for another community"
      subtitle="Gemini writes a fresh post — it does not copy the existing one."
      size="md"
      busy={busy}
      footer={(
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button variant="primary" icon="sparkles" onClick={submit} loading={busy} disabled={!options.length}>Generate new draft</Button>
        </>
      )}
    >
      <div className="stack">
        {options.length === 0 ? (
          <Callout tone="warning" title="No other communities" icon="community">
            Add another subreddit to {draft.project_name} before duplicating this angle.
          </Callout>
        ) : (
          <>
            <Field label="Target community">
              <select className="select" value={subredditId} onChange={(event) => setSubredditId(event.target.value)}>
                {options.map((community) => (
                  <option key={community.id} value={community.id}>r/{community.name} · {community.approval_status.replaceAll("_", " ")}</option>
                ))}
              </select>
            </Field>
            <Field label="Topic" hint="Adapt the angle for this community; avoid pasting the same content.">
              <input className="input" value={topic} onChange={(event) => setTopic(event.target.value)} maxLength={1000} />
            </Field>
            <Field label="Additional notes" optional>
              <textarea className="textarea" rows={3} value={notes} onChange={(event) => setNotes(event.target.value)} maxLength={1000} placeholder="What is different about this community's expectations?" />
            </Field>
            <Callout tone="info" icon="shield">The new draft starts as Pending Review with its own approval cycle.</Callout>
          </>
        )}
      </div>
    </Modal>
  );
}

function ManualPublishDialog({ draft, prepared, onClose, onPublished }) {
  const toast = useToast();
  const [url, setUrl] = useState("");
  const [note, setNote] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!confirmed) return toast.warning("Confirm first", "Tick the confirmation once the post exists on Reddit.");
    setBusy(true);
    try {
      await api.post(`/api/drafts/${draft.id}/publish/manual/confirm`, {
        url: url.trim(),
        note: note.trim(),
      });
      onPublished();
    } catch (error) {
      toast.error("Could not record publication", error.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      title="Publish manually"
      subtitle={`r/${prepared.subreddit} · RedditPilot does not submit anything here`}
      size="md"
      busy={busy}
      footer={(
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>Close</Button>
          <Button variant="primary" icon="checkCircle" onClick={submit} loading={busy} disabled={!confirmed}>Record publication</Button>
        </>
      )}
    >
      <div className="stack">
        <ol className="field-hint" style={{ paddingLeft: 18, lineHeight: 1.8 }}>
          {prepared.instructions.map((instruction) => <li key={instruction}>{instruction}</li>)}
        </ol>

        <div className="card" style={{ background: "rgba(0,0,0,.18)" }}>
          <div className="card-head" style={{ padding: "12px 14px 9px" }}>
            <div>
              <div className="section-label">Copy for Reddit</div>
              <div className="field-hint">Disclosure {prepared.disclosure_included ? "is included in the body" : "was not found in the body"}.</div>
            </div>
            <a className="btn btn-sm btn-outline" href={prepared.submit_url} target="_blank" rel="noreferrer">
              Open submit page <Icon name="external" size={12} />
            </a>
          </div>
          <div className="card-body" style={{ padding: 14 }}>
            <div className="row-between" style={{ marginBottom: 5 }}>
              <span className="section-label">Title</span>
              <CopyButton value={prepared.title} />
            </div>
            <p className="serif" style={{ fontSize: 15, lineHeight: 1.4 }}>{prepared.title}</p>
            <div className="row-between" style={{ margin: "12px 0 5px" }}>
              <span className="section-label">Body</span>
              <CopyButton value={prepared.body} />
            </div>
            <div className="preview-body" style={{ maxHeight: 220 }}>
              <p>{prepared.body}</p>
            </div>
          </div>
        </div>

        <Callout tone="warning" title="Record only after it is live" icon="alert">
          Paste the full Reddit post URL below. The URL must be for r/{prepared.subreddit} and contain <span className="mono">/comments/</span>.
        </Callout>

        <Field label="Reddit post URL">
          <input className="input" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://www.reddit.com/r/…/comments/…" />
        </Field>
        <Field label="Note" optional>
          <input className="input" value={note} onChange={(event) => setNote(event.target.value)} placeholder="Anything to remember about this publication" maxLength={1000} />
        </Field>
        <CheckRow checked={confirmed} onChange={setConfirmed}>
          I published this post on Reddit myself and the URL above is correct.
        </CheckRow>
      </div>
    </Modal>
  );
}

function ApiPublishDialog({ draft, check, onClose, onPublished }) {
  const toast = useToast();
  const [confirmed, setConfirmed] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!confirmed) return toast.warning("Confirm first", "API publishing requires explicit final confirmation.");
    setBusy(true);
    try {
      const result = await api.post(`/api/drafts/${draft.id}/publish/api`, {
        confirmation: true,
        note: note.trim(),
      });
      onPublished(result);
    } catch (error) {
      toast.error("API publishing failed", error.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      title="Submit through the Reddit API"
      subtitle={`r/${draft.subreddit_name} · one submission, no automatic retry`}
      size="md"
      busy={busy}
      footer={(
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button variant="primary" icon="send" onClick={submit} loading={busy} disabled={!confirmed}>Submit once</Button>
        </>
      )}
    >
      <div className="stack">
        <Callout tone="danger" title="This will publish immediately" icon="alert">
          Clicking “Submit once” sends this post to Reddit through your authorized account. There is no scheduled delay and no automatic retry. If the result is uncertain, the submission is recorded for manual resolution instead of retrying.
        </Callout>

        <div className="card" style={{ background: "rgba(0,0,0,.18)", padding: 13 }}>
          <dl className="kv" style={{ gridTemplateColumns: "120px 1fr" }}>
            <dt>Account</dt><dd>u/{check?.has_credentials ? "configured account" : "not configured"}</dd>
            <dt>Community</dt><dd>r/{draft.subreddit_name}</dd>
            <dt>Title</dt><dd style={{ textAlign: "left" }}>{draft.title}</dd>
            <dt>Approval</dt><dd>{draft.is_approved ? "Valid for this version" : "Missing"}</dd>
            <dt>Body length</dt><dd>{formatNumber((draft.body || "").length)} characters</dd>
          </dl>
        </div>

        <div className="issue-list">
          {(check?.api_blockers || []).slice(0, 8).map((reason) => (
            <div key={reason} className="issue warning"><Icon name="alert" size={13} /><div>{reason}</div></div>
          ))}
        </div>

        <Field label="Publication note" optional>
          <input className="input" value={note} onChange={(event) => setNote(event.target.value)} placeholder="e.g. Friday launch post" maxLength={500} />
        </Field>

        <CheckRow checked={confirmed} onChange={setConfirmed}>
          I have legitimate access to this Reddit account and API application, I have reviewed the post and the community rules, and I authorize this single submission.
        </CheckRow>
      </div>
    </Modal>
  );
}
