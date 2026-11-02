import React, { useMemo, useState } from "react";
import { api, qs } from "../api.js";
import Icon from "../components/Icons.jsx";
import { BarChart, HBarList, LineChart } from "../components/charts.jsx";
import {
  Badge,
  Button,
  Callout,
  EmptyState,
  ErrorBlock,
  LoadingBlock,
  PageHead,
} from "../components/ui.jsx";
import { useLoad } from "../hooks.js";
import { compactNumber, formatDate, formatNumber } from "../utils.js";

export default function Analytics({ projectId, projects, navigate }) {
  const [weeks, setWeeks] = useState(12);
  const query = useLoad(
    () => api.get(`/api/analytics${qs({ project_id: projectId || undefined, weeks })}`),
    [projectId, weeks]
  );
  const data = query.data;
  const summary = data?.summary || {};
  const weekly = data?.weekly || [];

  const chartData = useMemo(() => weekly.map((row) => ({
    ...row,
    label: new Date(`${row.week_start}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" }),
    postsLabel: `${row.posts} post${row.posts === 1 ? "" : "s"}`,
  })), [weekly]);

  const previous = weekly.at(-2);
  const latest = weekly.at(-1);
  const upvoteDelta = latest && previous ? latest.upvotes - previous.upvotes : null;
  const projectName = projects.find((project) => String(project.id) === String(projectId))?.name;

  const recent = data?.recent_posts || [];
  const hasPosts = (summary.total_posts || 0) > 0;

  return (
    <div className="page">
      <PageHead
        eyebrow="Analytics"
        title="Evidence, entered by hand."
        description={projectName
          ? `What the recorded data says about ${projectName}. Metrics are snapshots you enter after checking Reddit and your own website analytics.`
          : "A clear view of manually recorded publication data. No automatic tracking is implied, and no missing numbers are invented."}
        actions={(
          <>
            <div className="segmented">
              {[8, 12, 26].map((value) => (
                <button key={value} type="button" className={weeks === value ? "active" : ""} onClick={() => setWeeks(value)}>
                  {value} weeks
                </button>
              ))}
            </div>
            <Button variant="outline" icon="refresh" onClick={query.reload}>Refresh</Button>
          </>
        )}
      />

      <Callout tone="info" title="Where this data comes from" icon="info">
        {data?.disclaimer || "Upvotes, comments and views are entered by you. RedditPilot does not scrape Reddit or track visitors."}
      </Callout>

      {query.loading ? (
        <div className="grid grid-4" style={{ marginTop: 16 }}>
          {[0, 1, 2, 3].map((index) => <div key={index} className="stat"><LoadingBlock lines={2} /></div>)}
        </div>
      ) : query.error ? (
        <div className="card" style={{ marginTop: 16 }}><ErrorBlock message={query.error} onRetry={query.reload} /></div>
      ) : (
        <>
          <div className="stat-grid" style={{ marginTop: 16 }}>
            <div className="stat">
              <span className="stat-label">Posts recorded</span>
              <span className="stat-value">{summary.total_posts ?? 0}</span>
              <span className="stat-meta">{summary.manual_mode_posts ?? 0} manual · {summary.api_mode_posts ?? 0} API</span>
            </div>
            <div className="stat">
              <span className="stat-label">Upvotes</span>
              <span className="stat-value">{compactNumber(summary.total_upvotes)}</span>
              <span className={`stat-meta ${upvoteDelta > 0 ? "sage" : upvoteDelta < 0 ? "red" : ""}`}>
                <Icon name={upvoteDelta >= 0 ? "trendingUp" : "chart"} size={12} />
                {upvoteDelta == null ? "No prior week" : `${upvoteDelta >= 0 ? "+" : ""}${formatNumber(upvoteDelta)} vs prior week`}
              </span>
            </div>
            <div className="stat">
              <span className="stat-label">Comments</span>
              <span className="stat-value">{compactNumber(summary.total_comments)}</span>
              <span className="stat-meta">Avg {summary.avg_comments ?? 0} per post</span>
            </div>
            <div className="stat">
              <span className="stat-label">Website visits</span>
              <span className="stat-value">{compactNumber(summary.total_website_visits)}</span>
              <span className="stat-meta">CTR {summary.avg_ctr != null ? `${summary.avg_ctr}%` : "—"} · {compactNumber(summary.total_views)} views</span>
            </div>
          </div>

          {!hasPosts ? (
            <div className="card" style={{ marginTop: 16 }}>
              <EmptyState
                icon="chart"
                title="No published data yet"
                text="Analytics become meaningful after your first publication. Publish a draft, record the Reddit URL, then add metrics in Published Posts."
                actions={<Button variant="primary" icon="queue" onClick={() => navigate("queue")}>Open the draft queue</Button>}
              />
            </div>
          ) : (
            <>
              <div className="grid grid-2-1" style={{ marginTop: 16 }}>
                <div className="card">
                  <div className="card-head">
                    <div>
                      <h2 className="card-title">Engagement over time</h2>
                      <div className="card-sub">Weekly totals from recorded snapshots</div>
                    </div>
                    <Badge tone="neutral">{weeks} weeks</Badge>
                  </div>
                  <div className="card-body">
                    <LineChart
                      data={chartData}
                      series={[
                        { key: "upvotes", label: "Upvotes", color: "#e0784f" },
                        { key: "comments", label: "Comments", color: "#84a9c6" },
                      ]}
                      height={244}
                    />
                  </div>
                  <div className="card-foot">Each point is the total for that calendar week in your browser's local timezone.</div>
                </div>

                <div className="card">
                  <div className="card-head">
                    <div>
                      <h2 className="card-title">Comparison</h2>
                      <div className="card-sub">Upvotes by community</div>
                    </div>
                  </div>
                  <div className="card-body">
                    <HBarList
                      rows={(data?.by_subreddit || []).map((row) => ({ label: `r/${row.subreddit}`, value: row.upvotes }))}
                      empty="No community data yet."
                    />
                    <div className="divider" style={{ margin: "16px 0" }} />
                    <div className="row-between" style={{ marginBottom: 6 }}>
                      <span className="section-label">Publishing mode</span>
                      <span className="field-hint">{summary.total_posts} posts</span>
                    </div>
                    <div className="split-bar">
                      <i style={{ width: `${summary.total_posts ? (summary.manual_mode_posts / summary.total_posts) * 100 : 0}%`, background: "var(--accent)" }} />
                      <i style={{ width: `${summary.total_posts ? (summary.api_mode_posts / summary.total_posts) * 100 : 0}%`, background: "var(--blue)" }} />
                    </div>
                    <div className="legend-list">
                      <div className="legend-item"><i style={{ background: "var(--accent)" }} />Manual <strong>{summary.manual_mode_posts}</strong></div>
                      <div className="legend-item"><i style={{ background: "var(--blue)" }} />API <strong>{summary.api_mode_posts}</strong></div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="grid grid-2-1" style={{ marginTop: 16 }}>
                <div className="card">
                  <div className="card-head">
                    <div>
                      <h2 className="card-title">Referral traffic</h2>
                      <div className="card-sub">Optional manual website entries</div>
                    </div>
                  </div>
                  <div className="card-body">
                    <LineChart
                      data={chartData}
                      series={[
                        { key: "website_visits", label: "Website visits", color: "#93b48c" },
                        { key: "referral_visits", label: "Referral visits", color: "#d6a15e" },
                      ]}
                      height={224}
                    />
                  </div>
                  <div className="card-foot">If you do not enter website data, these lines stay at zero. That is not a failure signal.</div>
                </div>

                <div className="card">
                  <div className="card-head">
                    <div>
                      <h2 className="card-title">Weekly volume</h2>
                      <div className="card-sub">Published posts per week</div>
                    </div>
                  </div>
                  <div className="card-body">
                    <BarChart
                      data={chartData.map((row) => ({ label: row.label, value: row.posts }))}
                      height={224}
                      unit="posts"
                      highlightLast
                    />
                  </div>
                </div>
              </div>

              <div className="card" style={{ marginTop: 16 }}>
                <div className="card-head">
                  <div>
                    <h2 className="card-title">By community</h2>
                    <div className="card-sub">Aggregated from every recorded post</div>
                  </div>
                  <Badge tone="neutral">{(data?.by_subreddit || []).length} communities</Badge>
                </div>
                {(data?.by_subreddit || []).length === 0 ? (
                  <EmptyState icon="community" title="No community breakdown" text="Recorded publications will be grouped here." />
                ) : (
                  <div className="table-wrap">
                    <table className="data">
                      <thead>
                        <tr><th>Community</th><th className="num">Posts</th><th className="num">Upvotes</th><th className="num">Comments</th><th className="num">Views</th><th className="num">Visits</th><th className="num">Referrals</th><th>Share of upvotes</th></tr>
                      </thead>
                      <tbody>
                        {(data.by_subreddit || []).map((row) => {
                          const total = data.by_subreddit.reduce((sum, item) => sum + item.upvotes, 0);
                          const share = total ? Math.round((row.upvotes / total) * 100) : 0;
                          return (
                            <tr key={row.subreddit}>
                              <td className="strong">r/{row.subreddit}</td>
                              <td className="num">{row.posts}</td>
                              <td className="num">{formatNumber(row.upvotes)}</td>
                              <td className="num">{formatNumber(row.comments)}</td>
                              <td className="num">{formatNumber(row.views)}</td>
                              <td className="num">{formatNumber(row.website_visits)}</td>
                              <td className="num">{formatNumber(row.referral_visits)}</td>
                              <td style={{ minWidth: 120 }}>
                                <div className="row" style={{ gap: 7 }}>
                                  <div className="meter" style={{ width: 70 }}><div className="meter-fill" style={{ width: `${share}%` }} /></div>
                                  <span className="muted" style={{ fontSize: 10.5 }}>{share}%</span>
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              <div className="card" style={{ marginTop: 16 }}>
                <div className="card-head">
                  <div>
                    <h2 className="card-title">Recently recorded</h2>
                    <div className="card-sub">The latest metric snapshots</div>
                  </div>
                  <Button size="sm" variant="ghost" iconRight="arrowRight" onClick={() => navigate("published")}>All posts</Button>
                </div>
                <div className="table-wrap">
                  <table className="data">
                    <thead>
                      <tr><th>Post</th><th>Community</th><th>Published</th><th className="num">Upvotes</th><th className="num">Comments</th><th className="num">CTR</th></tr>
                    </thead>
                    <tbody>
                      {recent.map((post) => (
                        <tr key={post.id}>
                          <td className="table-title truncate" style={{ maxWidth: 340 }}>{post.title}</td>
                          <td className="text-soft">r/{post.subreddit_name}</td>
                          <td className="muted nowrap">{formatDate(post.published_at)}</td>
                          <td className="num">{formatNumber(post.upvotes)}</td>
                          <td className="num">{formatNumber(post.comments)}</td>
                          <td className="num">{post.ctr != null ? `${post.ctr}%` : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
