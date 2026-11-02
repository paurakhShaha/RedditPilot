import React from "react";
import { api, qs } from "../api.js";
import Icon from "../components/Icons.jsx";
import { BarChart, SparkBars } from "../components/charts.jsx";
import {
  Badge,
  Button,
  Callout,
  EmptyState,
  ErrorBlock,
  PageHead,
  StatusBadge,
} from "../components/ui.jsx";
import { useLoad } from "../hooks.js";
import { formatDate, formatDateTime, formatNumber, timeAgo } from "../utils.js";

function activityIcon(action = "", level = "info") {
  if (level === "error") return "alertCircle";
  if (level === "warning") return "alert";
  if (action.startsWith("draft.approved")) return "checkCircle";
  if (action.startsWith("published") || action.startsWith("reddit")) return "send";
  if (action.startsWith("schedule")) return "calendar";
  if (action.startsWith("subreddit")) return "community";
  if (action.startsWith("project")) return "folder";
  if (action.startsWith("settings")) return "settings";
  if (action.startsWith("gemini")) return "sparkles";
  return "circleDot";
}

export default function Overview({ projects, projectId, settings, navigate, refreshKey }) {
  const { data, loading, error, reload } = useLoad(
    () => api.get(`/api/overview${qs({ project_id: projectId || undefined })}`),
    [projectId, refreshKey]
  );

  const projectName = projects.find((project) => String(project.id) === String(projectId))?.name;
  const today = new Intl.DateTimeFormat(undefined, {
    weekday: "long", month: "long", day: "numeric",
  }).format(new Date());

  if (!projects.length && !loading) {
    return (
      <div className="page">
        <PageHead
          eyebrow="Welcome to RedditPilot"
          title="A human-in-the-loop Reddit workspace."
          description="Plan a small number of genuinely useful posts, review every word, and publish deliberately. Nothing here posts itself."
          actions={<Button variant="primary" icon="plus" onClick={() => navigate("projects")}>Create your first project</Button>}
        />
        <div className="card">
          <EmptyState
            icon="compass"
            title="Start with a project"
            text="A project holds your product brief, the communities you want to participate in, and every draft and publication record. Add your own project — RedditPilot ships with no sample data."
            actions={(
              <>
                <Button variant="primary" icon="folder" onClick={() => navigate("projects")}>Create a project</Button>
                <Button variant="outline" icon="settings" onClick={() => navigate("settings")}>Configure Gemini</Button>
              </>
            )}
          />
          <div className="grid grid-3" style={{ padding: "0 22px 24px" }}>
            {[
              ["01", "Describe the project", "Add an honest product brief, audience, and the claims you must avoid."],
              ["02", "Study the communities", "Record each subreddit's self-promotion and link rules, then re-verify them."],
              ["03", "Review, approve, publish", "AI drafts stay pending. You approve one exact version and publish it yourself."],
            ].map(([number, title, text]) => (
              <div key={number} className="card" style={{ background: "rgba(0,0,0,.12)", padding: 18 }}>
                <div className="mono" style={{ color: "var(--accent)", marginBottom: 8 }}>{number}</div>
                <div className="serif" style={{ fontSize: 16, marginBottom: 5 }}>{title}</div>
                <p className="field-hint">{text}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page">
        <PageHead eyebrow={today} title="Overview" />
        <div className="card"><ErrorBlock message={error} onRetry={reload} /></div>
      </div>
    );
  }

  const weekly = (data?.weekly_activity || []).map((row) => ({
    label: new Date(`${row.week_start}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" }),
    value: row.posts,
  }));
  const thisWeek = data?.weekly_activity?.at(-1)?.posts || 0;
  const limit = settings?.weekly_frequency || 1;
  const recent = data?.recent_published || [];
  const upcoming = data?.upcoming_scheduled || [];
  const activity = data?.recent_activity || [];

  return (
    <div className="page">
      <PageHead
        eyebrow={today}
        title={projectName ? `${projectName}, at a glance.` : "A quieter way to publish."}
        description={
          projectName
            ? `The working state of ${projectName}: what is waiting for your review, what is scheduled, and what has already shipped.`
            : "Everything across your workspace: drafts awaiting a human decision, the weekly plan, and the record of what was published."
        }
        actions={(
          <>
            <Button variant="outline" icon="queue" onClick={() => navigate("queue")}>Review queue</Button>
            <Button variant="primary" icon="sparkles" onClick={() => navigate("studio")}>Generate a draft</Button>
          </>
        )}
      />

      {data?.pending_with_blockers > 0 && (
        <Callout tone="warning" title={`${data.pending_with_blockers} pending draft${data.pending_with_blockers === 1 ? " has" : "s have"} compliance blockers`} icon="shield">
          Open the draft queue to resolve them. Approval and publishing stay blocked until every blocker is cleared.
        </Callout>
      )}

      <div className="stat-grid" style={{ marginTop: data?.pending_with_blockers > 0 ? 16 : 0 }}>
        <button type="button" className="stat" style={{ textAlign: "left", cursor: "pointer", color: "inherit" }} onClick={() => navigate("queue")}>
          <span className="stat-label">Pending review</span>
          <span className="stat-value">{data?.pending_approvals ?? "—"}</span>
          <span className={`stat-meta ${data?.pending_with_blockers ? "amber" : ""}`}>
            <Icon name="shield" size={12} />
            {data?.pending_with_blockers ? `${data.pending_with_blockers} with blockers` : "No blockers reported"}
          </span>
          <span className="stat-spark"><SparkBars values={weekly.map((row) => row.value)} width={58} height={24} /></span>
        </button>
        <button type="button" className="stat" style={{ textAlign: "left", cursor: "pointer", color: "inherit" }} onClick={() => navigate("queue")}>
          <span className="stat-label">Approved & ready</span>
          <span className="stat-value">{data?.approved_drafts ?? "—"}</span>
          <span className="stat-meta sage"><Icon name="checkCircle" size={12} />Approval is version-specific</span>
        </button>
        <button type="button" className="stat" style={{ textAlign: "left", cursor: "pointer", color: "inherit" }} onClick={() => navigate("published")}>
          <span className="stat-label">Published all-time</span>
          <span className="stat-value">{data?.published_posts ?? "—"}</span>
          <span className="stat-meta"><Icon name="send" size={12} />{thisWeek} this week · limit {limit}</span>
        </button>
        <button type="button" className="stat" style={{ textAlign: "left", cursor: "pointer", color: "inherit" }} onClick={() => navigate("calendar")}>
          <span className="stat-label">Scheduled ahead</span>
          <span className="stat-value">{data?.scheduled_posts ?? "—"}</span>
          <span className="stat-meta"><Icon name="calendar" size={12} />Drafts only — never auto-posts</span>
        </button>
      </div>

      <div className="grid grid-2-1" style={{ marginTop: 16 }}>
        <div className="card">
          <div className="card-head">
            <div>
              <h2 className="card-title">Weekly publishing rhythm</h2>
              <div className="card-sub">Published posts over the last eight weeks</div>
            </div>
            <Badge tone={thisWeek >= limit ? "amber" : "sage"} dot>
              {thisWeek}/{limit} this week
            </Badge>
          </div>
          <div className="card-body">
            <BarChart data={weekly} height={218} highlightLast unit="posts" />
          </div>
          <div className="card-foot">
            One considered post a week is a pacing rule, not a guarantee of Reddit compliance.
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <div>
              <h2 className="card-title">Next on the calendar</h2>
              <div className="card-sub">Scheduler-generated review slots</div>
            </div>
            <IconButtonLink onClick={() => navigate("calendar")} />
          </div>
          <div className="card-body tight">
            {upcoming.length === 0 ? (
              <EmptyState
                icon="calendar"
                title="No slots ahead"
                text="Configure a weekly plan for a project in the Publishing Calendar."
                actions={<Button size="sm" variant="outline" onClick={() => navigate("calendar")}>Open calendar</Button>}
              />
            ) : (
              <div className="stack-sm">
                {upcoming.map((slot) => (
                  <button
                    key={slot.id}
                    type="button"
                    className="row"
                    style={{ width: "100%", textAlign: "left", background: "transparent", border: 0, padding: "9px 2px", borderBottom: "1px solid var(--line-soft)" }}
                    onClick={() => slot.draft_id ? navigate("queue", { focusDraft: slot.draft_id }) : navigate("calendar")}
                  >
                    <div style={{ width: 38, flex: "none", textAlign: "center", borderRight: "1px solid var(--line-soft)", paddingRight: 9 }}>
                      <div className="mono" style={{ color: "var(--accent)", fontSize: 9.5, textTransform: "uppercase" }}>
                        {new Date(slot.slot_start).toLocaleDateString(undefined, { month: "short" })}
                      </div>
                      <div className="serif" style={{ fontSize: 19, lineHeight: 1.1 }}>{new Date(slot.slot_start).getDate()}</div>
                    </div>
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div className="truncate" style={{ fontSize: 12.5, color: "var(--text)" }}>
                        {slot.draft_title || `r/${slot.subreddit_name}`}
                      </div>
                      <div className="row" style={{ gap: 6, marginTop: 3 }}>
                        <StatusBadge status={slot.status} />
                        <span className="muted" style={{ fontSize: 10 }}>r/{slot.subreddit_name}</span>
                      </div>
                    </div>
                    <Icon name="chevronRight" size={14} style={{ color: "var(--muted)" }} />
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="card-foot">Slots create drafts for your review. They do not publish.</div>
        </div>
      </div>

      <div className="grid grid-2-1" style={{ marginTop: 16 }}>
        <div className="card">
          <div className="card-head">
            <div>
              <h2 className="card-title">Recently published</h2>
              <div className="card-sub">The last five records, with manually entered metrics</div>
            </div>
            <Button size="sm" variant="ghost" iconRight="arrowRight" onClick={() => navigate("published")}>All posts</Button>
          </div>
          {recent.length === 0 ? (
            <EmptyState icon="send" title="Nothing published yet" text="After you publish a post yourself, record it here to keep an honest log." />
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr><th>Post</th><th>Community</th><th className="num">Upvotes</th><th className="num">Comments</th><th>Published</th></tr>
                </thead>
                <tbody>
                  {recent.map((post) => (
                    <tr key={post.id} onClick={() => navigate("published")} style={{ cursor: "pointer" }}>
                      <td>
                        <div className="table-title truncate" style={{ maxWidth: 330 }}>{post.title}</div>
                        <div className="row" style={{ gap: 6, marginTop: 3 }}>
                          <Badge tone={post.mode === "api" ? "blue" : "neutral"}>{post.mode === "api" ? "API" : "Manual"}</Badge>
                          {post.status === "uncertain" && <Badge tone="amber">Needs resolution</Badge>}
                        </div>
                      </td>
                      <td className="text-soft">r/{post.subreddit_name}</td>
                      <td className="num">{formatNumber(post.upvotes)}</td>
                      <td className="num">{formatNumber(post.comments)}</td>
                      <td className="muted nowrap">{formatDate(post.published_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="card-foot">Metrics are entered by you. RedditPilot does not scrape Reddit or claim automatic tracking.</div>
        </div>

        <div className="card">
          <div className="card-head">
            <div>
              <h2 className="card-title">Workspace journal</h2>
              <div className="card-sub">Every approval, edit and publication</div>
            </div>
            <Button size="sm" variant="ghost" iconRight="arrowRight" onClick={() => navigate("settings")}>Full log</Button>
          </div>
          <div className="card-body">
            {activity.length === 0 ? (
              <p className="field-hint">No activity recorded yet.</p>
            ) : (
              <div className="activity-list">
                {activity.slice(0, 6).map((entry) => (
                  <div className="activity-item" key={entry.id}>
                    <div className={`activity-mark ${entry.level}`}><Icon name={activityIcon(entry.action, entry.level)} size={12} /></div>
                    <div className="activity-copy">
                      <p>{entry.message}</p>
                      <time>{timeAgo(entry.created_at)}</time>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-3" style={{ marginTop: 16 }}>
        <div className="card">
          <div className="card-head"><div><h2 className="card-title">AI usage</h2><div className="card-sub">This calendar month</div></div></div>
          <div className="card-body">
            <div className="stat-value" style={{ fontSize: 30 }}>{data?.ai_usage?.generations_this_month ?? 0}<small>drafts</small></div>
            <div className="stack-sm mt-12">
              {(data?.ai_usage?.by_model || []).length === 0 && <span className="field-hint">No generations yet.</span>}
              {(data?.ai_usage?.by_model || []).map((row) => (
                <div className="row-between" key={row.model}>
                  <span className="mono muted">{row.model}</span>
                  <span className="badge badge-neutral">{row.count}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
        <div className="card">
          <div className="card-head"><div><h2 className="card-title">Rules hygiene</h2><div className="card-sub">Community notes need refreshing</div></div></div>
          <div className="card-body">
            <div className="stat-value" style={{ fontSize: 30 }}>{data?.rules_unverified ?? 0}<small>unverified</small></div>
            <p className="field-hint mt-12">
              {data?.subreddit_count || 0} communities tracked. Verification older than 90 days raises a warning; older than 180 days blocks publishing.
            </p>
            <Button size="sm" variant="outline" className="mt-12" onClick={() => navigate("communities")}>Review communities</Button>
          </div>
        </div>
        <div className="card">
          <div className="card-head"><div><h2 className="card-title">The house rule</h2><div className="card-sub">Why the queue exists</div></div></div>
          <div className="card-body">
            <p className="serif" style={{ fontSize: 17, lineHeight: 1.5, color: "var(--text-soft)" }}>
              “Publishing is a human act. The machine may draft; it may not decide.”
            </p>
            <p className="field-hint mt-12">{data?.compliance_note}</p>
          </div>
        </div>
      </div>
    </div>
  );
}

function IconButtonLink({ onClick }) {
  return (
    <button type="button" className="btn btn-icon btn-sm" onClick={onClick} aria-label="Open calendar">
      <Icon name="arrowUpRight" size={14} />
    </button>
  );
}
