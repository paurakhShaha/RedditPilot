import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import Icon from "../components/Icons.jsx";
import {
  Badge,
  Button,
  Callout,
  CheckRow,
  ConfirmDialog,
  Field,
  IconButton,
  PageHead,
  Switch,
  ToggleRow,
  useToast,
} from "../components/ui.jsx";
import { useLoad } from "../hooks.js";
import { formatDateTime, timeAgo } from "../utils.js";

const TIMEZONES = [
  "Asia/Kathmandu",
  "Asia/Kolkata",
  "Asia/Dubai",
  "Asia/Singapore",
  "Asia/Tokyo",
  "Europe/London",
  "Europe/Berlin",
  "Europe/Lisbon",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "Australia/Sydney",
  "UTC",
];

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export default function Settings({ projects, settings, reloadSettings, refresh, navigate }) {
  const toast = useToast();
  const [ai, setAi] = useState(null);
  const [schedule, setSchedule] = useState(null);
  const [mode, setMode] = useState(null);
  const [reddit, setReddit] = useState(null);
  const [geminiKey, setGeminiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const [redditAck, setRedditAck] = useState(false);
  const [busy, setBusy] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [verifyInfo, setVerifyInfo] = useState(null);

  const activityQuery = useLoad(() => api.get("/api/settings/activity?limit=40"), []);

  useEffect(() => {
    if (!settings) return;
    setAi({
      gemini_model: settings.gemini_model || "gemini-2.5-flash",
      generation_temperature: settings.generation_temperature ?? 0.75,
      max_promo_score: settings.max_promo_score ?? 3,
      avoid_emojis: settings.avoid_emojis ?? true,
      default_include_link: settings.default_include_link ?? false,
      extra_generation_notes: settings.extra_generation_notes || "",
    });
    setSchedule({
      default_project_id: settings.default_project_id ?? "",
      weekly_frequency: settings.weekly_frequency ?? 1,
      publishing_day: settings.publishing_day ?? 0,
      publishing_time: settings.publishing_time || "10:00",
      timezone: settings.timezone || "Asia/Kathmandu",
      scheduling_paused: settings.scheduling_paused ?? false,
    });
    setMode({
      publishing_mode: settings.publishing_mode || "manual",
      api_publishing_enabled: settings.api_publishing_enabled ?? false,
    });
    setReddit({
      client_id: "",
      client_secret: "",
      username: "",
      password: "",
      refresh_token: "",
      user_agent: "",
    });
  }, [settings]);

  const afterSave = (message, detail) => {
    toast.success(message, detail);
    reloadSettings();
    refresh();
  };

  const patch = async (payload, successTitle, successDetail, key) => {
    setBusy(key);
    try {
      await api.patch("/api/settings", payload);
      afterSave(successTitle, successDetail);
    } catch (error) {
      toast.error("Could not save settings", error.message);
    } finally {
      setBusy(null);
    }
  };

  const saveAi = async () => {
    if (!ai) return;
    const payload = {
      gemini_model: ai.gemini_model.trim(),
      generation_temperature: Number(ai.generation_temperature),
      max_promo_score: Number(ai.max_promo_score),
      avoid_emojis: ai.avoid_emojis,
      default_include_link: ai.default_include_link,
      extra_generation_notes: ai.extra_generation_notes,
    };
    if (geminiKey.trim()) payload.gemini_api_key = geminiKey.trim();
    await patch(payload, "AI settings saved", geminiKey.trim() ? "The API key is stored encrypted in the local database." : "Generation preferences updated.", "ai");
    setGeminiKey("");
  };

  const testGemini = async () => {
    setBusy("test");
    try {
      const result = await api.post("/api/settings/test-gemini");
      toast.success("Gemini connected", result.message);
      reloadSettings();
    } catch (error) {
      toast.error("Gemini test failed", error.message);
    } finally {
      setBusy(null);
    }
  };

  const saveMode = async () => {
    if (!mode) return;
    if (mode.api_publishing_enabled && !settings.api_publishing_enabled && !acknowledged) {
      return toast.warning("Acknowledgement required", "Confirm the API requirements before enabling API publishing.");
    }
    await patch({
      publishing_mode: mode.publishing_mode,
      api_publishing_enabled: mode.api_publishing_enabled,
      api_enable_acknowledged: acknowledged,
    }, "Publishing settings saved", mode.publishing_mode === "manual" ? "Manual mode is active. API submission is unavailable." : (mode.api_publishing_enabled ? "API mode is active; every submission still requires review and final confirmation." : "API mode selected, but API publishing remains disabled."), "mode");
  };

  const saveReddit = async () => {
    if (!reddit) return;
    const hasAny = Object.values(reddit).some((value) => value.trim());
    if (!hasAny) return toast.warning("Nothing to save", "Enter at least one Reddit credential. Existing values are preserved when fields are blank.");
    await patch({ reddit }, "Reddit credentials saved", "Secrets are encrypted at rest and never returned by the API.", "reddit");
  };

  const verifyReddit = async () => {
    setBusy("verify");
    try {
      const result = await api.post("/api/reddit/verify");
      setVerifyInfo(result);
      toast.success("Reddit account verified", `Connected as u/${result.username}. No post was submitted.`);
      reloadSettings();
    } catch (error) {
      toast.error("Reddit verification failed", error.message);
    } finally {
      setBusy(null);
    }
  };

  const clearReddit = async () => {
    setBusy("clear-reddit");
    try {
      await api.patch("/api/settings", { clear_reddit_credentials: true });
      setConfirm(null);
      toast.success("Reddit credentials cleared", "The stored secrets were removed from the database.");
      reloadSettings();
      refresh();
    } catch (error) {
      toast.error("Could not clear credentials", error.message);
    } finally {
      setBusy(null);
    }
  };

  const clearGemini = async () => {
    setBusy("clear-gemini");
    try {
      await api.patch("/api/settings", { clear_gemini_key: true });
      setConfirm(null);
      toast.success("Gemini key removed", "Add a new key before generating again.");
      reloadSettings();
      refresh();
    } catch (error) {
      toast.error("Could not remove key", error.message);
    } finally {
      setBusy(null);
    }
  };

  const saveSchedule = async () => {
    if (!schedule) return;
    await patch({
      default_project_id: schedule.default_project_id === "" ? null : Number(schedule.default_project_id),
      weekly_frequency: Number(schedule.weekly_frequency),
      publishing_day: Number(schedule.publishing_day),
      publishing_time: schedule.publishing_time,
      timezone: schedule.timezone,
      scheduling_paused: schedule.scheduling_paused,
    }, "Schedule saved", "The authoritative schedule lives in the database; restarts do not duplicate slots.", "schedule");
  };

  const download = async (path, name, key) => {
    setBusy(key);
    try {
      const filename = await api.download(path, name);
      toast.success("Download ready", filename);
    } catch (error) {
      toast.error("Download failed", error.message);
    } finally {
      setBusy(null);
    }
  };

  if (!settings || !ai || !schedule || !mode || !reddit) {
    return (
      <div className="page">
        <PageHead eyebrow="Settings" title="Configuration." />
        <div className="card"><div className="card-body"><div className="skeleton" style={{ height: 240 }} /></div></div>
      </div>
    );
  }

  const activeProjects = projects.filter((project) => !project.is_archived);

  return (
    <div className="page">
      <PageHead
        eyebrow="Settings"
        title="The instrument panel."
        description="Configuration lives locally. API publishing is off by default, credentials are encrypted, and no setting can make the scheduler approve or publish a post."
        actions={(
          <>
            <Badge tone={settings.gemini_key_configured ? "sage" : "red"} dot>Gemini {settings.gemini_key_configured ? "ready" : "missing key"}</Badge>
            <Badge tone={settings.publishing_mode === "api" ? "blue" : "neutral"} dot>{settings.publishing_mode === "api" ? "API mode" : "Manual mode"}</Badge>
            <Button variant="outline" icon="download" onClick={() => download("/api/settings/export", "redditpilot-export.json", "export")} loading={busy === "export"}>Export data</Button>
          </>
        )}
      />

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-body" style={{ padding: "16px 20px" }}>
          <div className="grid grid-4" style={{ gap: 14 }}>
            {[
              ["Gemini", settings.gemini_key_configured ? "Configured" : "Missing key", settings.gemini_key_configured ? "green" : "red", settings.gemini_key_source === "environment" ? "From .env" : "Encrypted in database"],
              ["Publishing", settings.publishing_mode === "api" ? "API mode" : "Manual mode", settings.publishing_mode === "api" ? "ember" : "green", settings.publishing_mode === "api" ? (settings.api_publishing_enabled ? "API enabled" : "API disabled") : "Copy & submit yourself"],
              ["Reddit", settings.reddit_connected ? `u/${settings.reddit_username}` : settings.reddit_credentials_configured ? "Credentials saved" : "Not connected", settings.reddit_connected ? "green" : settings.reddit_credentials_configured ? "ember" : "red", settings.reddit_last_verified_at ? `Verified ${timeAgo(settings.reddit_last_verified_at)}` : "Optional"],
              ["Scheduler", settings.scheduling_paused ? "Paused" : "Active", settings.scheduling_paused ? "red" : "green", `${settings.weekly_frequency}× per week · ${settings.timezone}`],
            ].map(([label, value, dot, detail]) => (
              <div key={label} className="row" style={{ alignItems: "flex-start", gap: 8 }}>
                <span className={`dot ${dot}`} style={{ marginTop: 5 }} />
                <div>
                  <div className="section-label">{label}</div>
                  <div style={{ fontSize: 12.5, color: "var(--text-soft)", marginTop: 2 }}>{value}</div>
                  <div className="field-hint">{detail}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="stack">
        <div className="card">
          <div className="setting-section">
            <div className="setting-section-head">
              <div className="eyebrow">01 · Intelligence</div>
              <h3>Gemini & generation</h3>
              <p>The model writes first drafts only. Nothing it returns is approved, scheduled for publication, or posted.</p>
            </div>
            <div className="setting-section-body">
              <div className="form-grid">
                <Field label="Gemini model" hint="For example gemini-2.5-flash or gemini-2.5-pro.">
                  <input className="input" value={ai.gemini_model} onChange={(event) => setAi((current) => ({ ...current, gemini_model: event.target.value }))} maxLength={120} />
                </Field>
                <Field label="API key" hint={settings.gemini_key_configured ? `A key is configured (${settings.gemini_key_source}). Leave blank to keep it.` : "Stored encrypted in the local database."}>
                  <div className="input-wrap">
                    <input
                      className="input"
                      type={showKey ? "text" : "password"}
                      value={geminiKey}
                      onChange={(event) => setGeminiKey(event.target.value)}
                      placeholder={settings.gemini_key_configured ? "•••••••••••• (unchanged)" : "Paste API key"}
                      autoComplete="off"
                    />
                    <button type="button" className="reveal" onClick={() => setShowKey((value) => !value)} aria-label={showKey ? "Hide key" : "Show key"}>
                      <Icon name={showKey ? "eyeOff" : "eye"} size={14} />
                    </button>
                  </div>
                </Field>
              </div>
              <div className="row">
                <Button size="sm" variant="outline" icon="sparkles" onClick={testGemini} loading={busy === "test"}>Test connection</Button>
                {settings.gemini_key_configured && (
                  <Button size="sm" variant="ghost" icon="trash" onClick={() => setConfirm("gemini")}>Remove stored key</Button>
                )}
                {settings.gemini_key_source === "environment" && (
                  <span className="field-hint">The key currently comes from GEMINI_API_KEY in .env.</span>
                )}
              </div>
              <hr className="divider" />
              <div className="form-grid">
                <Field label="Temperature" hint="Lower is more literal; higher is more varied.">
                  <input
                    className="input"
                    type="number"
                    min="0"
                    max="1.5"
                    step="0.05"
                    value={ai.generation_temperature}
                    onChange={(event) => setAi((current) => ({ ...current, generation_temperature: event.target.value }))}
                  />
                </Field>
                <Field label="Maximum promotional intensity" hint="The compliance engine blocks drafts above this score (1–5).">
                  <select className="select" value={ai.max_promo_score} onChange={(event) => setAi((current) => ({ ...current, max_promo_score: event.target.value }))}>
                    {[1, 2, 3, 4, 5].map((value) => <option key={value} value={value}>{value} / 5</option>)}
                  </select>
                </Field>
              </div>
              <ToggleRow title="Avoid emojis" description="Prefer plain editorial copy by default." checked={ai.avoid_emojis} onChange={(value) => setAi((current) => ({ ...current, avoid_emojis: value }))} />
              <ToggleRow title="Include a project link when allowed" description="Only used for scheduled drafts where the community explicitly allows promotion with disclosure." checked={ai.default_include_link} onChange={(value) => setAi((current) => ({ ...current, default_include_link: value }))} />
              <Field label="Extra generation notes" optional hint="Appended to every prompt. Keep it short and specific.">
                <textarea className="textarea" rows={3} maxLength={3000} value={ai.extra_generation_notes} onChange={(event) => setAi((current) => ({ ...current, extra_generation_notes: event.target.value }))} placeholder="e.g. Write in British English. Prefer concrete examples over metaphors." />
              </Field>
              <div className="row" style={{ justifyContent: "flex-end" }}>
                <Button variant="primary" icon="check" onClick={saveAi} loading={busy === "ai"}>Save AI settings</Button>
              </div>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="setting-section">
            <div className="setting-section-head">
              <div className="eyebrow">02 · Publishing</div>
              <h3>Two deliberate modes</h3>
              <p>Manual mode is the default and needs no Reddit credentials. API mode is optional, off by default, and still requires a human approval plus final confirmation for every post.</p>
            </div>
            <div className="setting-section-body">
              <div className="grid grid-2" style={{ gap: 10 }}>
                <button type="button" className={`publish-option ${mode.publishing_mode === "manual" ? "selected" : ""}`} onClick={() => setMode((current) => ({ ...current, publishing_mode: "manual" }))}>
                  <div className="publish-option-head">
                    <Icon name="copy" size={16} style={{ color: mode.publishing_mode === "manual" ? "var(--accent)" : "var(--muted)" }} />
                    <strong>Manual</strong>
                    {mode.publishing_mode === "manual" && <Badge tone="ember">Selected</Badge>}
                  </div>
                  <p>RedditPilot prepares the exact title and body. You submit on Reddit yourself, then paste the post URL to record it. Recommended default.</p>
                </button>
                <button type="button" className={`publish-option ${mode.publishing_mode === "api" ? "selected" : ""}`} onClick={() => setMode((current) => ({ ...current, publishing_mode: "api" }))}>
                  <div className="publish-option-head">
                    <Icon name="send" size={16} style={{ color: mode.publishing_mode === "api" ? "var(--accent)" : "var(--muted)" }} />
                    <strong>Reddit API</strong>
                    {mode.publishing_mode === "api" && <Badge tone="ember">Selected</Badge>}
                  </div>
                  <p>Submit through your own authorized Reddit API app. Requires credentials, explicit enablement, suitable community status, and a final confirmation every time.</p>
                </button>
              </div>

              {mode.publishing_mode === "api" && (
                <Callout tone="warning" title="API access is your responsibility" icon="alert">
                  Use a legitimate Reddit API application and follow Reddit's terms, rate limits and commercial-use requirements. Never use multiple accounts, evade bans, manipulate engagement, or mass-post. RedditPilot submits one approved post at a time and never retries automatically.
                </Callout>
              )}

              <ToggleRow
                title="Enable API publishing"
                description="Off by default. Manual mode remains safe to use without this."
                checked={mode.api_publishing_enabled}
                onChange={(value) => setMode((current) => ({ ...current, api_publishing_enabled: value }))}
              />
              {mode.api_publishing_enabled && !settings.api_publishing_enabled && (
                <CheckRow checked={acknowledged} onChange={setAcknowledged}>
                  I confirm I have legitimate Reddit API access, will comply with Reddit's terms and commercial-use rules, and will review every post before submitting it.
                </CheckRow>
              )}
              <div className="row" style={{ justifyContent: "flex-end" }}>
                <Button variant="primary" icon="check" onClick={saveMode} loading={busy === "mode"}>Save publishing mode</Button>
              </div>

              <hr className="divider" />

              <div className="row-between">
                <div>
                  <div className="section-label">Reddit connection</div>
                  <div className="field-hint" style={{ marginTop: 3 }}>
                    {settings.reddit_connected
                      ? `Connected as u/${settings.reddit_username}. Verified ${settings.reddit_last_verified_at ? timeAgo(settings.reddit_last_verified_at) : "recently"}.`
                      : settings.reddit_credentials_configured
                        ? `Credentials saved. Status: ${settings.reddit_status}.`
                        : "No Reddit credentials configured. Manual mode works without them."}
                  </div>
                </div>
                <div className="row" style={{ gap: 6 }}>
                  <Badge tone={settings.reddit_connected ? "sage" : settings.reddit_credentials_configured ? "amber" : "neutral"} dot>
                    {settings.reddit_connected ? "Connected" : settings.reddit_credentials_configured ? "Unverified" : "Not configured"}
                  </Badge>
                  {settings.reddit_credentials_configured && (
                    <>
                      <Button size="sm" variant="outline" icon="shield" onClick={verifyReddit} loading={busy === "verify"}>Verify account</Button>
                      <Button size="sm" variant="ghost" icon="trash" onClick={() => setConfirm("reddit")}>Clear</Button>
                    </>
                  )}
                </div>
              </div>
              {settings.reddit_last_error && <Callout tone="warning" title="Last Reddit error" icon="alertCircle">{settings.reddit_last_error}</Callout>}
              {verifyInfo && <Callout tone="success" title="Verified" icon="checkCircle">Connected as u/{verifyInfo.username}. Verification never submits a post.</Callout>}

              <div className="form-grid">
                <Field label="Client ID" hint="From your Reddit app settings.">
                  <input className="input" value={reddit.client_id} onChange={(event) => setReddit((current) => ({ ...current, client_id: event.target.value }))} placeholder="Leave blank to keep current" autoComplete="off" />
                </Field>
                <Field label="Client secret">
                  <input className="input" type="password" value={reddit.client_secret} onChange={(event) => setReddit((current) => ({ ...current, client_secret: event.target.value }))} placeholder="Leave blank to keep current" autoComplete="new-password" />
                </Field>
                <Field label="Username" hint="Without u/.">
                  <input className="input" value={reddit.username} onChange={(event) => setReddit((current) => ({ ...current, username: event.target.value }))} placeholder="your_reddit_name" autoComplete="off" />
                </Field>
                <Field label="Password" hint="Optional when using a refresh token.">
                  <input className="input" type="password" value={reddit.password} onChange={(event) => setReddit((current) => ({ ...current, password: event.target.value }))} placeholder="Leave blank to keep current" autoComplete="new-password" />
                </Field>
                <Field label="Refresh token" optional hint="Preferred over a password for script apps.">
                  <input className="input" type="password" value={reddit.refresh_token} onChange={(event) => setReddit((current) => ({ ...current, refresh_token: event.target.value }))} placeholder="Leave blank to keep current" autoComplete="new-password" />
                </Field>
                <Field label="User agent" hint="A descriptive string, e.g. redditpilot/1.0 by u/yourname.">
                  <input className="input" value={reddit.user_agent} onChange={(event) => setReddit((current) => ({ ...current, user_agent: event.target.value }))} placeholder="redditpilot/1.0 by u/yourname" maxLength={300} />
                </Field>
              </div>
              <div className="row" style={{ justifyContent: "space-between" }}>
                <span className="field-hint">Encrypted with Fernet at rest. Secrets are never returned by the API.</span>
                <Button variant="outline" icon="key" onClick={saveReddit} loading={busy === "reddit"}>Save credentials</Button>
              </div>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="setting-section">
            <div className="setting-section-head">
              <div className="eyebrow">03 · Cadence</div>
              <h3>Weekly schedule</h3>
              <p>Slots are persistent and timezone-aware. The scheduler generates review drafts inside a 72-hour lead window — it cannot approve or publish them.</p>
            </div>
            <div className="setting-section-body">
              <div className="form-grid">
                <Field label="Default project" optional hint="Used as the initial project in the dashboard.">
                  <select className="select" value={schedule.default_project_id} onChange={(event) => setSchedule((current) => ({ ...current, default_project_id: event.target.value }))}>
                    <option value="">No default</option>
                    {activeProjects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
                  </select>
                </Field>
                <Field label="Posts per week" hint="1–3. One is recommended for genuine participation.">
                  <select className="select" value={schedule.weekly_frequency} onChange={(event) => setSchedule((current) => ({ ...current, weekly_frequency: event.target.value }))}>
                    {[1, 2, 3].map((value) => <option key={value} value={value}>{value} per week</option>)}
                  </select>
                </Field>
                <Field label="Publishing day">
                  <select className="select" value={schedule.publishing_day} onChange={(event) => setSchedule((current) => ({ ...current, publishing_day: event.target.value }))}>
                    {DAYS.map((day, index) => <option key={day} value={index}>{day}</option>)}
                  </select>
                </Field>
                <Field label="Publishing time">
                  <input className="input" type="time" value={schedule.publishing_time} onChange={(event) => setSchedule((current) => ({ ...current, publishing_time: event.target.value }))} />
                </Field>
                <Field label="Timezone" hint="IANA timezone. Slots are stored in UTC and displayed in this zone.">
                  <select className="select" value={schedule.timezone} onChange={(event) => setSchedule((current) => ({ ...current, timezone: event.target.value }))}>
                    {!TIMEZONES.includes(schedule.timezone) && <option value={schedule.timezone}>{schedule.timezone}</option>}
                    {TIMEZONES.map((zone) => <option key={zone} value={zone}>{zone}</option>)}
                  </select>
                </Field>
              </div>
              <ToggleRow
                title="Pause scheduling"
                description="Stops new slots and draft generation. Scheduled drafts also cannot be published while paused."
                checked={schedule.scheduling_paused}
                onChange={(value) => setSchedule((current) => ({ ...current, scheduling_paused: value }))}
              />
              <div className="row" style={{ justifyContent: "flex-end" }}>
                <Button variant="primary" icon="check" onClick={saveSchedule} loading={busy === "schedule"}>Save schedule</Button>
              </div>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="setting-section">
            <div className="setting-section-head">
              <div className="eyebrow">04 · Stewardship</div>
              <h3>Data, backups & journal</h3>
              <p>Everything lives in a local SQLite database. Export JSON for portability; download a SQLite backup before upgrades.</p>
            </div>
            <div className="setting-section-body">
              <div className="grid grid-2" style={{ gap: 10 }}>
                <div className="card" style={{ background: "rgba(0,0,0,.14)", padding: 14 }}>
                  <div className="row" style={{ gap: 8, marginBottom: 5 }}><Icon name="download" size={16} style={{ color: "var(--accent)" }} /><strong style={{ fontSize: 12.5 }}>Export workspace JSON</strong></div>
                  <p className="field-hint">Projects, communities, drafts, revisions, approvals, schedules and metrics. Secrets are excluded.</p>
                  <Button size="sm" variant="outline" className="mt-12" icon="download" onClick={() => download("/api/settings/export", "redditpilot-export.json", "export")} loading={busy === "export"}>Download JSON</Button>
                </div>
                <div className="card" style={{ background: "rgba(0,0,0,.14)", padding: 14 }}>
                  <div className="row" style={{ gap: 8, marginBottom: 5 }}><Icon name="database" size={16} style={{ color: "var(--sage)" }} /><strong style={{ fontSize: 12.5 }}>SQLite backup</strong></div>
                  <p className="field-hint">A consistent copy of the database file. Store it securely; it contains encrypted credentials.</p>
                  <Button size="sm" variant="outline" className="mt-12" icon="download" onClick={() => download("/api/settings/backup", "redditpilot-backup.db", "backup")} loading={busy === "backup"}>Download backup</Button>
                </div>
              </div>
              <Callout tone="warning" title="Back up the encryption key too" icon="key">
                API keys and Reddit credentials are encrypted with the key in <span className="mono">data/.secret_key</span> (or <span className="mono">APP_SECRET_KEY</span>). A database backup alone cannot decrypt them on another machine.
              </Callout>

              <div className="row-between" style={{ marginTop: 4 }}>
                <div>
                  <div className="section-label">Activity journal</div>
                  <div className="field-hint" style={{ marginTop: 2 }}>The latest {activityQuery.data?.items?.length || 0} events. Also written to logs/redditpilot.log.</div>
                </div>
                <Button size="sm" variant="ghost" icon="refresh" onClick={activityQuery.reload}>Refresh log</Button>
              </div>
              <div className="card" style={{ background: "rgba(0,0,0,.12)", maxHeight: 340, overflowY: "auto" }}>
                <div className="card-body" style={{ padding: "12px 15px" }}>
                  {activityQuery.loading ? (
                    <div className="skeleton" style={{ height: 80 }} />
                  ) : (activityQuery.data?.items || []).length === 0 ? (
                    <p className="field-hint">No activity yet.</p>
                  ) : (
                    <div className="activity-list">
                      {(activityQuery.data.items || []).map((entry) => (
                        <div className="activity-item" key={entry.id}>
                          <div className={`activity-mark ${entry.level}`}>
                            <Icon name={entry.level === "error" ? "alertCircle" : entry.level === "warning" ? "alert" : "circleDot"} size={11} />
                          </div>
                          <div className="activity-copy">
                            <p>{entry.message}</p>
                            <time>{formatDateTime(entry.created_at)} · {entry.action}</time>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="setting-section">
            <div className="setting-section-head">
              <div className="eyebrow">05 · Boundaries</div>
              <h3>What this tool will not do</h3>
              <p>The product is deliberately constrained. These are not settings you can turn off.</p>
            </div>
            <div className="setting-section-body">
              <div className="grid grid-2" style={{ gap: 9 }}>
                {[
                  "Approve a draft on your behalf",
                  "Publish automatically or on a schedule",
                  "Retry an uncertain API submission",
                  "Mass-post, scrape, or evade a ban",
                  "Use multiple accounts or fake engagement",
                  "Bypass weekly limits or stale rules",
                ].map((item) => (
                  <div key={item} className="row" style={{ alignItems: "flex-start", gap: 8, fontSize: 12, color: "var(--text-mid)" }}>
                    <Icon name="xCircle" size={14} style={{ color: "var(--red)", flex: "none", marginTop: 1 }} />
                    {item}
                  </div>
                ))}
              </div>
              <Callout tone="info" title="A personal pacing rule is not a compliance guarantee" icon="shield">
                One post a week helps you participate deliberately, but every community's rules still apply. RedditPilot surfaces the rules you recorded; you remain responsible for the live rules and Reddit's terms.
              </Callout>
            </div>
          </div>
        </div>
      </div>

      <ConfirmDialog
        open={confirm === "gemini"}
        onClose={() => setConfirm(null)}
        onConfirm={clearGemini}
        tone="danger"
        icon="trash"
        title="Remove the stored Gemini key?"
        message="Draft generation will fail until a new key is added. Existing drafts are unaffected."
        confirmLabel="Remove key"
        busy={busy === "clear-gemini"}
      />
      <ConfirmDialog
        open={confirm === "reddit"}
        onClose={() => setConfirm(null)}
        onConfirm={clearReddit}
        tone="danger"
        icon="trash"
        title="Clear all Reddit credentials?"
        message="The encrypted client ID, secret, username, password and refresh token will be deleted from the database. Manual publishing continues to work without credentials."
        confirmLabel="Clear credentials"
        busy={busy === "clear-reddit"}
      />
    </div>
  );
}
