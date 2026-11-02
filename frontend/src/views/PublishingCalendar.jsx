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
  LoadingBlock,
  Modal,
  PageHead,
  StatusBadge,
  Switch,
  useToast,
} from "../components/ui.jsx";
import { useLoad } from "../hooks.js";
import {
  MONTHS,
  WEEKDAYS,
  addMonths,
  formatDate,
  formatDateTime,
  formatTime,
  localDateKey,
  monthCells,
  startOfMonth,
  timeAgo,
} from "../utils.js";

const OBJECTIVES = [
  "Introduce a new project",
  "Share a useful resource",
  "Ask for constructive feedback",
  "Share a development story",
  "Discuss an interesting technical challenge",
  "Present a project launch",
  "Share a lesson learned",
];

const POST_TYPES = ["Text post", "Discussion", "Question", "Project showcase", "Tutorial", "Feedback request"];

export default function PublishingCalendar({ projects, projectId, setProjectId, settings, navigate, refresh }) {
  const toast = useToast();
  const activeProjects = projects.filter((project) => !project.is_archived);
  const effective = activeProjects.find((project) => String(project.id) === String(projectId)) || activeProjects[0];
  const effectiveId = effective?.id;

  const [cursor, setCursor] = useState(() => startOfMonth(new Date()));
  const [slot, setSlot] = useState(null);
  const [skipTarget, setSkipTarget] = useState(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [planForm, setPlanForm] = useState({
    subreddit_id: "",
    objective: "Share a development story",
    post_type: "Text post",
    topic_hint: "",
    enabled: true,
  });
  const [planBusy, setPlanBusy] = useState(false);

  const planQuery = useLoad(
    () => api.get(`/api/schedule/plan/${effectiveId}`),
    [effectiveId],
    { skip: !effectiveId }
  );
  const scheduleQuery = useLoad(
    () => api.get(`/api/schedule${qs({ project_id: effectiveId, limit: 300 })}`),
    [effectiveId],
    { skip: !effectiveId }
  );
  const communityQuery = useLoad(
    () => api.get(`/api/subreddits?project_id=${effectiveId}`),
    [effectiveId],
    { skip: !effectiveId }
  );

  const slots = scheduleQuery.data?.items || [];
  const communities = communityQuery.data?.items || [];
  const plan = planQuery.data?.plan;
  const configured = plan?.configured;

  useEffect(() => {
    if (!plan) return;
    setPlanForm({
      subreddit_id: plan.subreddit_id ? String(plan.subreddit_id) : "",
      objective: plan.objective || "Share a development story",
      post_type: plan.post_type || "Text post",
      topic_hint: plan.topic_hint || "",
      enabled: plan.enabled !== false,
    });
  }, [plan?.project_id, plan?.subreddit_id, plan?.objective, plan?.post_type, plan?.topic_hint, plan?.enabled, configured]);

  const reloadAll = () => {
    planQuery.reload();
    scheduleQuery.reload();
    refresh();
  };

  const savePlan = async () => {
    if (!effectiveId) return;
    if (!planForm.subreddit_id) return toast.warning("Choose a community", "The weekly plan needs a target subreddit.");
    setPlanBusy(true);
    try {
      await api.put(`/api/schedule/plan/${effectiveId}`, {
        subreddit_id: Number(planForm.subreddit_id),
        objective: planForm.objective,
        post_type: planForm.post_type,
        topic_hint: planForm.topic_hint.trim(),
        enabled: planForm.enabled,
      });
      toast.success("Weekly plan saved", planForm.enabled ? "Upcoming slots have been materialized. Drafts appear in the review window." : "The plan is saved but disabled, so no new slots will generate.");
      reloadAll();
    } catch (error) {
      toast.error("Could not save the plan", error.message);
    } finally {
      setPlanBusy(false);
    }
  };

  const togglePause = async () => {
    setActionBusy(true);
    try {
      const result = await api.post("/api/schedule/pause", { paused: !settings?.scheduling_paused });
      toast.info(result.paused ? "Scheduling paused" : "Scheduling resumed", result.paused ? "No new drafts will be generated until resumed." : "The scheduler can create review drafts again.");
      reloadAll();
    } catch (error) {
      toast.error("Could not update scheduling", error.message);
    } finally {
      setActionBusy(false);
    }
  };

  const runTick = async () => {
    setActionBusy(true);
    try {
      const result = await api.post("/api/schedule/tick");
      if (result.paused) toast.warning("Scheduler is paused", "Resume scheduling before running a tick.");
      else toast.success("Scheduler tick complete", `${result.materialized || 0} slot(s) materialized, ${result.generated || 0} draft(s) generated, ${result.failed || 0} failed. Nothing was published.`);
      reloadAll();
    } catch (error) {
      toast.error("Scheduler tick failed", error.message);
    } finally {
      setActionBusy(false);
    }
  };

  const skip = async () => {
    if (!skipTarget) return;
    setActionBusy(true);
    try {
      await api.post(`/api/schedule/slots/${skipTarget.id}/skip`);
      toast.info("Slot skipped", "No draft will be generated for this date.");
      setSkipTarget(null);
      setSlot(null);
      reloadAll();
    } catch (error) {
      toast.error("Could not skip slot", error.message);
    } finally {
      setActionBusy(false);
    }
  };

  const retry = async (target) => {
    setActionBusy(true);
    try {
      const result = await api.post(`/api/schedule/slots/${target.id}/retry`);
      toast.success("Draft generated", result.draft_id ? `Draft #${result.draft_id} is waiting in the review queue.` : "The slot was retried.");
      setSlot(null);
      reloadAll();
    } catch (error) {
      toast.error("Retry failed", error.message);
    } finally {
      setActionBusy(false);
    }
  };

  const cells = useMemo(() => monthCells(cursor), [cursor]);
  const slotsByDay = useMemo(() => {
    const map = new Map();
    slots.forEach((item) => {
      const key = localDateKey(item.slot_start);
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(item);
    });
    return map;
  }, [slots]);

  const upcoming = useMemo(() => {
    const now = Date.now();
    return slots
      .filter((item) => new Date(item.slot_start).getTime() >= now && !["skipped", "published"].includes(item.status))
      .sort((a, b) => new Date(a.slot_start) - new Date(b.slot_start))
      .slice(0, 8);
  }, [slots]);

  const monthSlots = slots.filter((item) => {
    const date = new Date(item.slot_start);
    return date.getFullYear() === cursor.getFullYear() && date.getMonth() === cursor.getMonth();
  });

  if (!activeProjects.length) {
    return (
      <div className="page">
        <PageHead eyebrow="Publishing Calendar" title="A cadence, not a content mill." description="The weekly scheduler creates a small number of review drafts. It never publishes." />
        <div className="card">
          <EmptyState icon="folder" title="Create a project first" text="Schedules are per project, so each product keeps its own cadence and community plan." actions={<Button variant="primary" icon="folder" onClick={() => navigate("projects")}>Create a project</Button>} />
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <PageHead
        eyebrow="Publishing Calendar"
        title="A steady, human-reviewed cadence."
        description="One slot a week by default, in your timezone. The scheduler writes drafts up to 72 hours ahead and stops there — every slot still needs your review and approval."
        actions={(
          <>
            <Button variant="outline" icon={settings?.scheduling_paused ? "play" : "pause"} onClick={togglePause} loading={actionBusy}>
              {settings?.scheduling_paused ? "Resume scheduling" : "Pause scheduling"}
            </Button>
            <Button variant="outline" icon="refresh" onClick={runTick} loading={actionBusy}>Run tick now</Button>
            <Button variant="primary" icon="studio" onClick={() => navigate("studio")}>Write manually</Button>
          </>
        )}
      />

      <Callout tone="ember" title="The scheduler only creates drafts" icon="shield">
        No path in this calendar can approve or publish a post. Slots are generated as Pending Review; publication stays a separate, explicit human action with final confirmation.
      </Callout>

      {settings?.scheduling_paused && (
        <Callout tone="warning" title="Scheduling is paused" icon="pause">
          Existing slots remain visible, but no new slots or drafts are generated, and scheduled drafts cannot be published while paused.
        </Callout>
      )}

      <div className="calendar-layout" style={{ marginTop: 16 }}>
        <div className="stack">
          <div className="card">
            <div className="card-head">
              <div>
                <h2 className="card-title">Calendar</h2>
                <div className="card-sub">
                  {effective?.name} · times shown in {settings?.timezone || "Asia/Kathmandu"}
                </div>
              </div>
              <div className="row" style={{ gap: 6 }}>
                <select
                  className="select"
                  style={{ width: "auto", minWidth: 160 }}
                  value={effectiveId || ""}
                  onChange={(event) => setProjectId(event.target.value)}
                  aria-label="Calendar project"
                >
                  {activeProjects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
                </select>
                <div className="calendar-toolbar">
                  <Button variant="outline" size="sm" icon="chevronLeft" onClick={() => setCursor(addMonths(cursor, -1))} aria-label="Previous month" />
                  <button type="button" className="btn btn-sm btn-ghost calendar-month" onClick={() => setCursor(startOfMonth(new Date()))} title="Jump to this month">
                    {MONTHS[cursor.getMonth()]} {cursor.getFullYear()}
                  </button>
                  <Button variant="outline" size="sm" icon="chevronRight" onClick={() => setCursor(addMonths(cursor, 1))} aria-label="Next month" />
                </div>
              </div>
            </div>
            <div className="card-body tight">
              <div className="calendar">
                <div className="calendar-head">
                  {WEEKDAYS.map((day) => <div key={day}>{day.slice(0, 3)}</div>)}
                </div>
                <div className="calendar-grid">
                  {cells.map((day) => {
                    const key = localDateKey(day);
                    const daySlots = slotsByDay.get(key) || [];
                    const isThisMonth = day.getMonth() === cursor.getMonth();
                    const isToday = key === localDateKey(new Date());
                    return (
                      <div key={key} className={`calendar-cell ${isThisMonth ? "" : "dim"} ${isToday ? "today" : ""}`}>
                        <div className="day-num">{day.getDate()}</div>
                        {daySlots.slice(0, 3).map((item) => (
                          <button
                            key={item.id}
                            type="button"
                            className={`slot-chip status-${item.status}`}
                            onClick={() => setSlot(item)}
                            title={`${formatTime(item.slot_start)} · r/${item.subreddit_name} · ${item.status}`}
                          >
                            <span className="slot-time">{formatTime(item.slot_start)} · {item.status.replaceAll("_", " ")}</span>
                            <span className="slot-name">r/{item.subreddit_name}</span>
                          </button>
                        ))}
                        {daySlots.length > 3 && (
                          <button type="button" className="more-slots link-btn" onClick={() => setSlot(daySlots[3])}>+{daySlots.length - 3} more</button>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
            <div className="card-foot">
              {monthSlots.length} slot{monthSlots.length === 1 ? "" : "s"} this month · click a slot to inspect it. Slots never publish by themselves.
            </div>
          </div>

          <div className="card">
            <div className="card-head">
              <div>
                <h2 className="card-title">Upcoming slots</h2>
                <div className="card-sub">Generated ahead of time, waiting for the 72-hour drafting window</div>
              </div>
              <Badge tone="neutral">{upcoming.length}</Badge>
            </div>
            <div className="card-body tight">
              {upcoming.length === 0 ? (
                <p className="field-hint" style={{ padding: "10px 2px" }}>No upcoming slots. Save an enabled weekly plan to materialize slots.</p>
              ) : (
                <div className="stack-sm">
                  {upcoming.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      className="row-between"
                      style={{ width: "100%", background: "transparent", border: 0, borderBottom: "1px solid var(--line-soft)", padding: "9px 2px", textAlign: "left" }}
                      onClick={() => setSlot(item)}
                    >
                      <div>
                        <div className="row" style={{ gap: 6 }}>
                          <span style={{ fontSize: 12.5, color: "var(--text)" }}>{formatDate(item.slot_start, { weekday: "short" })} · {formatTime(item.slot_start)}</span>
                          <StatusBadge status={item.status} />
                        </div>
                        <div className="field-hint">r/{item.subreddit_name}{item.draft_title ? ` · ${item.draft_title}` : ""}</div>
                      </div>
                      <span className="field-hint nowrap">{item.draft_id ? "Draft ready" : `${Math.ceil((new Date(item.slot_start) - Date.now()) / 86400000)}d away`}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="stack">
          <div className="card">
            <div className="card-head">
              <div>
                <h2 className="card-title">Weekly plan</h2>
                <div className="card-sub">{effective?.name} · one considered post at a time</div>
              </div>
              <Icon name="calendar" size={17} style={{ color: "var(--accent)" }} />
            </div>
            {planQuery.loading ? (
              <div className="card-body"><LoadingBlock lines={4} /></div>
            ) : planQuery.error ? (
              <ErrorBlock message={planQuery.error} onRetry={planQuery.reload} />
            ) : (
              <>
                <div className="card-body">
                  {!configured && (
                    <Callout tone="warning" title="No plan configured" icon="alert">
                      Choose a community and save an enabled plan. RedditPilot will create weekly slots and generate drafts in the 72-hour lead window.
                    </Callout>
                  )}
                  <div className="stack" style={{ marginTop: configured ? 0 : 14 }}>
                    <Field label="Target community">
                      <select className="select" value={planForm.subreddit_id} onChange={(event) => setPlanForm((current) => ({ ...current, subreddit_id: event.target.value }))}>
                        <option value="" disabled>{communities.length ? "Choose a community" : "No communities yet"}</option>
                        {communities.map((community) => (
                          <option key={community.id} value={community.id} disabled={["prohibited", "not_recommended"].includes(community.approval_status)}>
                            r/{community.name}{["prohibited", "not_recommended"].includes(community.approval_status) ? " (off limits)" : ""}
                          </option>
                        ))}
                      </select>
                    </Field>
                    {communities.length === 0 && (
                      <button type="button" className="link-btn" onClick={() => navigate("communities")}>Add a community for this project →</button>
                    )}
                    <div className="form-grid">
                      <Field label="Objective">
                        <select className="select" value={planForm.objective} onChange={(event) => setPlanForm((current) => ({ ...current, objective: event.target.value }))}>
                          {OBJECTIVES.map((objective) => <option key={objective} value={objective}>{objective}</option>)}
                        </select>
                      </Field>
                      <Field label="Post type">
                        <select className="select" value={planForm.post_type} onChange={(event) => setPlanForm((current) => ({ ...current, post_type: event.target.value }))}>
                          {POST_TYPES.map((type) => <option key={type} value={type}>{type}</option>)}
                        </select>
                      </Field>
                    </div>
                    <Field label="Topic hint" optional hint="A recurring theme, or guidance the scheduler should use for every slot.">
                      <textarea className="textarea" rows={3} maxLength={1000} value={planForm.topic_hint} onChange={(event) => setPlanForm((current) => ({ ...current, topic_hint: event.target.value }))} placeholder="e.g. Lessons from building in public; share specific engineering trade-offs." />
                    </Field>
                    <div className="switch-row" style={{ padding: "6px 0", borderBottom: 0 }}>
                      <div className="switch-copy">
                        <strong>Plan enabled</strong>
                        <span>Disabled plans keep existing slots but generate no new drafts.</span>
                      </div>
                      <Switch checked={planForm.enabled} onChange={(value) => setPlanForm((current) => ({ ...current, enabled: value }))} label="Enable weekly plan" />
                    </div>
                  </div>
                </div>
                <div className="card-footer-actions">
                  <Button variant="ghost" size="sm" icon="refresh" onClick={reloadAll}>Reload</Button>
                  <Button variant="primary" size="sm" icon="check" onClick={savePlan} loading={planBusy}>Save plan</Button>
                </div>
              </>
            )}
          </div>

          <div className="card">
            <div className="card-head">
              <div>
                <h2 className="card-title">Cadence</h2>
                <div className="card-sub">From your global schedule settings</div>
              </div>
              <Button size="sm" variant="ghost" iconRight="arrowRight" onClick={() => navigate("settings")}>Edit</Button>
            </div>
            <div className="card-body">
              <dl className="kv" style={{ gridTemplateColumns: "1fr auto" }}>
                <dt>Frequency</dt><dd>{settings?.weekly_frequency || 1} per week</dd>
                <dt>Day</dt><dd>{WEEKDAYS[settings?.publishing_day ?? 0]}</dd>
                <dt>Time</dt><dd>{settings?.publishing_time || "10:00"}</dd>
                <dt>Timezone</dt><dd>{settings?.timezone || "Asia/Kathmandu"}</dd>
                <dt>Status</dt><dd>{settings?.scheduling_paused ? "Paused" : "Active"}</dd>
                <dt>Gemini</dt><dd>{settings?.gemini_key_configured ? "Configured" : "Missing key"}</dd>
              </dl>
              <div className="divider" style={{ margin: "14px 0" }} />
              <p className="field-hint">
                The background scheduler checks every {Math.max(1, 15)} minutes. Slots are stored in the database, so restarts do not create duplicates or lose the plan.
              </p>
            </div>
          </div>

          <Callout tone="info" title="What “generated” means" icon="info">
            Within 72 hours of a slot, the scheduler asks Gemini for a draft using the plan's objective and topic, then marks the slot “Draft ready”. The draft waits in the queue for you.
          </Callout>
        </div>
      </div>

      {slot && (
        <SlotModal
          slot={slot}
          settings={settings}
          busy={actionBusy}
          onClose={() => setSlot(null)}
          onOpenDraft={() => { navigate("queue", { focusDraft: slot.draft_id }); setSlot(null); }}
          onSkip={() => setSkipTarget(slot)}
          onRetry={() => retry(slot)}
        />
      )}

      <ConfirmDialog
        open={!!skipTarget}
        onClose={() => setSkipTarget(null)}
        onConfirm={skip}
        tone="danger"
        icon="calendar"
        title="Skip this slot?"
        message={`No draft will be generated for ${skipTarget ? formatDateTime(skipTarget.slot_start) : "this slot"}. Any existing draft link is kept, but the date is marked skipped.`}
        confirmLabel="Skip slot"
        busy={actionBusy}
      />
    </div>
  );
}

function SlotModal({ slot, settings, busy, onClose, onOpenDraft, onSkip, onRetry }) {
  const canRetry = !slot.draft_id && ["planned", "failed"].includes(slot.status) && !settings?.scheduling_paused;
  const canSkip = !["published", "skipped"].includes(slot.status);
  return (
    <Modal
      open
      onClose={onClose}
      title={formatDate(slot.slot_start, { weekday: "long" })}
      subtitle={`${formatTime(slot.slot_start)} · ${settings?.timezone || "Asia/Kathmandu"} · r/${slot.subreddit_name}`}
      size="sm"
      footer={(
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>Close</Button>
          {canSkip && <Button variant="danger" icon="calendar" onClick={onSkip} disabled={busy}>Skip slot</Button>}
          {canRetry && <Button variant="primary" icon="refresh" onClick={onRetry} loading={busy}>Retry generation</Button>}
          {slot.draft_id && <Button variant="primary" icon="eye" onClick={onOpenDraft} disabled={busy}>Open draft</Button>}
        </>
      )}
    >
      <div className="stack">
        <div className="row" style={{ gap: 7 }}>
          <StatusBadge status={slot.status} />
          <Badge tone="neutral">{slot.project_name}</Badge>
        </div>
        <dl className="kv" style={{ gridTemplateColumns: "110px 1fr" }}>
          <dt>Objective</dt><dd style={{ textAlign: "left" }}>{slot.objective}</dd>
          <dt>Post type</dt><dd style={{ textAlign: "left" }}>{slot.post_type}</dd>
          <dt>Topic hint</dt><dd style={{ textAlign: "left" }}>{slot.topic_hint || "None — the project brief is used"}</dd>
          <dt>Draft</dt><dd style={{ textAlign: "left" }}>{slot.draft_id ? `#${slot.draft_id} — ${slot.draft_status}` : "Not generated yet"}</dd>
          <dt>Created</dt><dd style={{ textAlign: "left" }}>{timeAgo(slot.created_at)}</dd>
        </dl>
        {slot.draft_title && (
          <div className="card" style={{ background: "rgba(0,0,0,.16)", padding: 12 }}>
            <div className="section-label" style={{ marginBottom: 3 }}>Draft title</div>
            <div className="serif" style={{ fontSize: 15 }}>{slot.draft_title}</div>
          </div>
        )}
        {slot.error && <Callout tone="warning" title="Scheduler note" icon="alert">{slot.error}</Callout>}
        <Callout tone="info" icon="shield">
          This slot cannot publish. Approving and posting happen only from the Draft Queue.
        </Callout>
      </div>
    </Modal>
  );
}
