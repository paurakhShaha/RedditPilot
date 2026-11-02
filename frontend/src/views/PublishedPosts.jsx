import React, { useMemo, useState } from "react";
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
import { formatDate, formatDateTime, formatNumber, safeHost } from "../utils.js";

export default function PublishedPosts({ projectId, navigate, refresh }) {
  const toast = useToast();
  const [statusFilter, setStatusFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [metricsPost, setMetricsPost] = useState(null);
  const [resolvePost, setResolvePost] = useState(null);
  const [detailPost, setDetailPost] = useState(null);

  const query = useLoad(
    () => api.get(`/api/published${qs({ project_id: projectId || undefined })}`),
    [projectId]
  );
  const items = query.data?.items || [];

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    return items.filter((post) => {
      if (statusFilter !== "all" && post.status !== statusFilter) return false;
      if (!term) return true;
      return `${post.title} ${post.subreddit_name} ${post.notes}`.toLowerCase().includes(term);
    });
  }, [items, statusFilter, search]);

  const summary = useMemo(() => {
    const published = items.filter((post) => post.status === "published");
    const views = published.reduce((sum, post) => sum + post.views, 0);
    const visits = published.reduce((sum, post) => sum + post.website_visits, 0);
    return {
      total: published.length,
      upvotes: published.reduce((sum, post) => sum + post.upvotes, 0),
      comments: published.reduce((sum, post) => sum + post.comments, 0),
      visits,
      ctr: views ? ((visits / views) * 100).toFixed(2) : null,
      uncertain: items.filter((post) => post.status === "uncertain").length,
    };
  }, [items]);

  const reload = () => { query.reload(); refresh(); };

  return (
    <div className="page">
      <PageHead
        eyebrow="Published Posts"
        title="The honest record."
        description="Every post you have published, with metrics you enter yourself after checking Reddit. No scraping, no implied tracking, no invented numbers."
        actions={(
          <>
            <Badge tone="neutral" dot>{summary.total} published</Badge>
            <Button variant="outline" icon="refresh" onClick={query.reload}>Refresh</Button>
            <Button variant="primary" icon="chart" onClick={() => navigate("analytics")}>Open analytics</Button>
          </>
        )}
      />

      <Callout tone="info" title="Manual metrics only" icon="info">
        RedditPilot does not connect to Reddit analytics or scrape counts. Update upvotes, comments and visits in this view whenever you want a new analytics snapshot.
      </Callout>

      <div className="stat-grid" style={{ marginTop: 16 }}>
        <div className="stat">
          <span className="stat-label">Published posts</span>
          <span className="stat-value">{summary.total}</span>
          <span className="stat-meta"><Icon name="send" size={12} />{summary.uncertain ? `${summary.uncertain} uncertain` : "All resolved"}</span>
        </div>
        <div className="stat">
          <span className="stat-label">Upvotes</span>
          <span className="stat-value">{formatNumber(summary.upvotes)}</span>
          <span className="stat-meta"><Icon name="trendingUp" size={12} />Across recorded posts</span>
        </div>
        <div className="stat">
          <span className="stat-label">Comments</span>
          <span className="stat-value">{formatNumber(summary.comments)}</span>
          <span className="stat-meta"><Icon name="message" size={12} />Conversation, not just reach</span>
        </div>
        <div className="stat">
          <span className="stat-label">Website visits</span>
          <span className="stat-value">{formatNumber(summary.visits)}</span>
          <span className="stat-meta"><Icon name="link" size={12} />CTR {summary.ctr ? `${summary.ctr}%` : "—"}</span>
        </div>
      </div>

      {summary.uncertain > 0 && (
        <Callout tone="warning" title={`${summary.uncertain} submission${summary.uncertain === 1 ? "" : "s"} need resolution`} icon="alertCircle">
          An API submission ended with an uncertain result. Check your Reddit profile, then confirm whether it was published. RedditPilot will never retry automatically.
        </Callout>
      )}

      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-head">
          <div className="row" style={{ gap: 10 }}>
            <div className="segmented">
              {[["all", "All"], ["published", "Published"], ["uncertain", "Uncertain"]].map(([value, label]) => (
                <button key={value} type="button" className={statusFilter === value ? "active" : ""} onClick={() => setStatusFilter(value)}>
                  {label}
                </button>
              ))}
            </div>
            <div className="input-wrap" style={{ minWidth: 230 }}>
              <span style={{ position: "absolute", left: 11, top: "50%", transform: "translateY(-50%)", color: "var(--muted)", display: "flex" }}>
                <Icon name="search" size={14} />
              </span>
              <input className="input" style={{ paddingLeft: 34 }} placeholder="Search posts…" value={search} onChange={(event) => setSearch(event.target.value)} />
            </div>
          </div>
          <span className="field-hint">{filtered.length} result{filtered.length === 1 ? "" : "s"}</span>
        </div>

        {query.loading ? (
          <div className="card-body"><LoadingBlock lines={5} height={28} /></div>
        ) : query.error ? (
          <ErrorBlock message={query.error} onRetry={query.reload} />
        ) : filtered.length === 0 ? (
          <EmptyState
            icon="send"
            title={items.length ? "No posts match this view" : "No publication records yet"}
            text={items.length ? "Clear the filter or search for a different phrase." : "Publish a draft manually or through the authorized API, then record it here. Manual publication starts in the Draft Queue."}
            actions={!items.length && <Button variant="primary" icon="queue" onClick={() => navigate("queue")}>Open draft queue</Button>}
          />
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Post</th>
                  <th>Community</th>
                  <th>Published</th>
                  <th>Mode</th>
                  <th className="num">Upvotes</th>
                  <th className="num">Comments</th>
                  <th className="num">Visits</th>
                  <th className="num">CTR</th>
                  <th style={{ width: 130 }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((post) => (
                  <tr key={post.id}>
                    <td style={{ maxWidth: 360 }}>
                      <button type="button" className="link-btn" style={{ color: "var(--text)", textAlign: "left", display: "block" }} onClick={() => setDetailPost(post)}>
                        <span className="table-title line-2">{post.title}</span>
                      </button>
                      <div className="row" style={{ gap: 5, marginTop: 4 }}>
                        {post.status === "uncertain" ? <StatusBadge status="uncertain" /> : <Badge tone="sage" dot>Published</Badge>}
                        {post.url && <span className="field-hint truncate" style={{ maxWidth: 200 }}>{safeHost(post.url)}</span>}
                      </div>
                    </td>
                    <td className="text-soft nowrap">r/{post.subreddit_name}</td>
                    <td className="muted nowrap">{formatDate(post.published_at)}</td>
                    <td><Badge tone={post.mode === "api" ? "blue" : "neutral"}>{post.mode === "api" ? "API" : "Manual"}</Badge></td>
                    <td className="num">{formatNumber(post.upvotes)}</td>
                    <td className="num">{formatNumber(post.comments)}</td>
                    <td className="num">{formatNumber(post.website_visits)}</td>
                    <td className="num">{post.ctr != null ? `${post.ctr}%` : "—"}</td>
                    <td>
                      <div className="row" style={{ gap: 2 }}>
                        {post.status === "published" && (
                          <IconButton icon="chart" label="Update metrics" size="sm" onClick={() => setMetricsPost(post)} />
                        )}
                        {post.status === "uncertain" && (
                          <Button size="sm" variant="outline" onClick={() => setResolvePost(post)}>Resolve</Button>
                        )}
                        {post.url && (
                          <a className="btn btn-icon btn-sm btn-ghost" href={post.url} target="_blank" rel="noreferrer" aria-label="Open on Reddit" title="Open on Reddit">
                            <Icon name="external" size={14} />
                          </a>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="card-foot">
          {query.data?.note || "Reddit metrics are entered manually. RedditPilot does not scrape or claim automatic tracking."}
        </div>
      </div>

      {metricsPost && (
        <MetricsModal
          post={metricsPost}
          onClose={() => setMetricsPost(null)}
          onSaved={() => {
            setMetricsPost(null);
            toast.success("Metrics recorded", "A new analytics snapshot was added to the post's history.");
            reload();
          }}
        />
      )}

      {resolvePost && (
        <ResolveModal
          post={resolvePost}
          onClose={() => setResolvePost(null)}
          onResolved={(message) => {
            setResolvePost(null);
            toast.success("Submission resolved", message);
            reload();
          }}
        />
      )}

      {detailPost && (
        <PostDetailModal
          post={detailPost}
          onClose={() => setDetailPost(null)}
          onMetrics={() => { setMetricsPost(detailPost); setDetailPost(null); }}
          onResolve={() => { setResolvePost(detailPost); setDetailPost(null); }}
        />
      )}
    </div>
  );
}

function MetricsModal({ post, onClose, onSaved }) {
  const toast = useToast();
  const [form, setForm] = useState({
    upvotes: post.upvotes ?? 0,
    comments: post.comments ?? 0,
    views: post.views ?? 0,
    website_visits: post.website_visits ?? 0,
    referral_visits: post.referral_visits ?? 0,
    notes: post.notes || "",
  });
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      await api.patch(`/api/published/${post.id}/metrics`, {
        upvotes: Number(form.upvotes) || 0,
        comments: Number(form.comments) || 0,
        views: Number(form.views) || 0,
        website_visits: Number(form.website_visits) || 0,
        referral_visits: Number(form.referral_visits) || 0,
        notes: form.notes,
      });
      onSaved();
    } catch (error) {
      toast.error("Could not update metrics", error.message);
    } finally {
      setBusy(false);
    }
  };

  const set = (key, value) => setForm((current) => ({ ...current, [key]: value }));

  return (
    <Modal
      open
      onClose={onClose}
      title="Update manual metrics"
      subtitle={`r/${post.subreddit_name} · published ${formatDate(post.published_at)}`}
      size="sm"
      busy={busy}
      footer={(
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button variant="primary" icon="check" onClick={submit} loading={busy}>Save snapshot</Button>
        </>
      )}
    >
      <div className="stack">
        <Callout tone="info" icon="info">
          Check the live Reddit post and your website analytics, then enter the current totals. Each save appends a timestamped snapshot.
        </Callout>
        <div className="form-grid">
          <Field label="Upvotes"><input className="input" type="number" min="0" value={form.upvotes} onChange={(event) => set("upvotes", event.target.value)} /></Field>
          <Field label="Comments"><input className="input" type="number" min="0" value={form.comments} onChange={(event) => set("comments", event.target.value)} /></Field>
          <Field label="Views" hint="Reddit's view count, if visible."><input className="input" type="number" min="0" value={form.views} onChange={(event) => set("views", event.target.value)} /></Field>
          <Field label="Website visits"><input className="input" type="number" min="0" value={form.website_visits} onChange={(event) => set("website_visits", event.target.value)} /></Field>
          <Field label="Referral visits" hint="Visits attributed to Reddit."><input className="input" type="number" min="0" value={form.referral_visits} onChange={(event) => set("referral_visits", event.target.value)} /></Field>
        </div>
        <Field label="Note" optional>
          <input className="input" value={form.notes} onChange={(event) => set("notes", event.target.value)} placeholder="e.g. 24-hour check" maxLength={2000} />
        </Field>
        {form.views > 0 && (
          <p className="field-hint">Computed CTR: {((Number(form.website_visits) / Number(form.views)) * 100).toFixed(2)}%</p>
        )}
      </div>
    </Modal>
  );
}

function ResolveModal({ post, onClose, onResolved }) {
  const toast = useToast();
  const [outcome, setOutcome] = useState("published");
  const [url, setUrl] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmNotPublished, setConfirmNotPublished] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      const result = await api.post(`/api/published/${post.id}/resolve`, {
        outcome,
        url: outcome === "published" ? url.trim() : null,
        note: note.trim(),
      });
      onResolved(result.message);
    } catch (error) {
      toast.error("Could not resolve submission", error.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Modal
        open
        onClose={onClose}
        title="Resolve an uncertain submission"
        subtitle="Check your Reddit profile before choosing an outcome."
        size="sm"
        busy={busy}
        footer={(
          <>
            <Button variant="ghost" onClick={onClose} disabled={busy}>Cancel</Button>
            <Button
              variant="primary"
              icon="check"
              onClick={() => outcome === "not_published" ? setConfirmNotPublished(true) : submit()}
              loading={busy}
              disabled={outcome === "published" && url.trim().length < 10}
            >
              {outcome === "published" ? "Confirm publication" : "Mark not published"}
            </Button>
          </>
        )}
      >
        <div className="stack">
          <div className="card" style={{ background: "rgba(0,0,0,.18)", padding: 12 }}>
            <div className="serif" style={{ fontSize: 15, lineHeight: 1.4 }}>{post.title}</div>
            <div className="field-hint">Submitted to r/{post.subreddit_name} via API · {formatDateTime(post.created_at)}</div>
          </div>
          <div className="grid grid-2" style={{ gap: 8 }}>
            <button type="button" className={`publish-option ${outcome === "published" ? "selected" : ""}`} onClick={() => setOutcome("published")}>
              <div className="publish-option-head"><Icon name="checkCircle" size={16} style={{ color: "var(--sage)" }} /><strong>It is live</strong></div>
              <p>I found the post on Reddit and want to record its URL.</p>
            </button>
            <button type="button" className={`publish-option ${outcome === "not_published" ? "selected" : ""}`} onClick={() => setOutcome("not_published")}>
              <div className="publish-option-head"><Icon name="xCircle" size={16} style={{ color: "var(--red)" }} /><strong>It was not posted</strong></div>
              <p>Nothing appeared. Remove the uncertain record and return the draft to Approved.</p>
            </button>
          </div>
          {outcome === "published" ? (
            <Field label="Reddit post URL">
              <input className="input" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://www.reddit.com/r/…/comments/…" />
            </Field>
          ) : (
            <Callout tone="warning" title="This deletes the uncertain record" icon="alert">
              The draft returns to Approved with its approval intact. Review it before trying any submission again — RedditPilot will not retry for you.
            </Callout>
          )}
          <Field label="Note" optional>
            <input className="input" value={note} onChange={(event) => setNote(event.target.value)} maxLength={1000} placeholder="What you found on Reddit" />
          </Field>
        </div>
      </Modal>
      <ConfirmDialog
        open={confirmNotPublished}
        onClose={() => setConfirmNotPublished(false)}
        onConfirm={() => { setConfirmNotPublished(false); submit(); }}
        tone="danger"
        icon="xCircle"
        title="Confirm it was not published"
        message="This removes the uncertain publication record and returns the draft to Approved. Only continue if you have verified that no post exists."
        confirmLabel="Yes, not published"
        busy={busy}
      />
    </>
  );
}

function PostDetailModal({ post, onClose, onMetrics, onResolve }) {
  const detail = useLoad(() => api.get(`/api/published/${post.id}`), [post.id]);
  const data = detail.data || post;
  return (
    <Modal
      open
      onClose={onClose}
      title="Publication record"
      subtitle={`r/${data.subreddit_name} · ${formatDateTime(data.published_at)}`}
      size="md"
      footer={(
        <>
          <Button variant="ghost" onClick={onClose}>Close</Button>
          {data.status === "published" && <Button variant="outline" icon="chart" onClick={onMetrics}>Update metrics</Button>}
          {data.status === "uncertain" && <Button variant="primary" icon="alertCircle" onClick={onResolve}>Resolve submission</Button>}
          {data.url && <a className="btn btn-primary" href={data.url} target="_blank" rel="noreferrer">Open on Reddit <Icon name="external" size={13} /></a>}
        </>
      )}
    >
      {detail.loading ? <LoadingBlock lines={5} height={22} /> : (
        <div className="stack">
          <h3 className="serif" style={{ fontSize: 22, lineHeight: 1.35 }}>{data.title}</h3>
          <div className="row" style={{ gap: 6 }}>
            <StatusBadge status={data.status} />
            <Badge tone={data.mode === "api" ? "blue" : "neutral"}>{data.mode === "api" ? "API submission" : "Manual publication"}</Badge>
            {data.reddit_post_id && <Badge tone="neutral">ID {data.reddit_post_id}</Badge>}
          </div>
          <div className="grid grid-4" style={{ gap: 8 }}>
            {[
              ["Upvotes", data.upvotes],
              ["Comments", data.comments],
              ["Views", data.views],
              ["Website visits", data.website_visits],
            ].map(([label, value]) => (
              <div key={label} className="card" style={{ background: "rgba(0,0,0,.16)", padding: 11 }}>
                <div className="section-label">{label}</div>
                <div className="serif" style={{ fontSize: 22 }}>{formatNumber(value)}</div>
              </div>
            ))}
          </div>
          {data.notes && <Callout tone="info" title="Notes" icon="file">{data.notes}</Callout>}
          {detail.data?.draft && (
            <div>
              <div className="section-label" style={{ marginBottom: 5 }}>Published copy</div>
              <div className="preview-body" style={{ maxHeight: 260 }}><p>{detail.data.draft.body}</p></div>
            </div>
          )}
          {(detail.data?.history || []).length > 0 && (
            <div>
              <div className="section-label" style={{ marginBottom: 5 }}>Metric history</div>
              <div className="table-wrap">
                <table className="data">
                  <thead><tr><th>Recorded</th><th className="num">Upvotes</th><th className="num">Comments</th><th className="num">Visits</th><th>Note</th></tr></thead>
                  <tbody>
                    {detail.data.history.slice(0, 8).map((row) => (
                      <tr key={row.id}>
                        <td className="muted nowrap">{formatDateTime(row.recorded_at)}</td>
                        <td className="num">{formatNumber(row.upvotes)}</td>
                        <td className="num">{formatNumber(row.comments)}</td>
                        <td className="num">{formatNumber(row.website_visits)}</td>
                        <td className="field-hint">{row.note || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}
