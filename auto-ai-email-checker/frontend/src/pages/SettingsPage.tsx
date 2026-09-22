import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  fetchClassifyPromptStatus,
  fetchClassifyTraining,
  fetchMailboxLabelStats,
  fetchMailboxLabelTimeline,
  fetchMailboxOutcomes,
  type ClassifyPromptStatus,
  type ClassifyTrainingExample,
  type LabelTimeline,
  type Mailbox,
  type MailboxLabelStats,
  type OutcomeEntry,
  type OutcomeLabel,
} from "../api";
import { CLASSIFY_LABELS, CLASSIFY_LABEL_TITLES } from "../labels";
import {
  FONT_FAMILIES,
  FONT_SIZES,
  INBOX_TYPES,
  VIEW_MODES,
  type FontFamily,
  type FontSize,
  type InboxType,
  type ViewMode,
} from "../prefs";
import type { ThemePref } from "../theme";
import AccountSelect from "../components/AccountSelect";
import CategoryLineChart from "../components/CategoryLineChart";
import DateTimeField from "../components/DateTimeField";
import LabelBarChart from "../components/LabelBarChart";
import LabelPieChart from "../components/LabelPieChart";

export type SettingsSection = "appearance" | "training" | "statistics";

const TRAINING_PAGE_SIZE = 20;

function pad2(value: number): string {
  return String(value).padStart(2, "0");
}

function toDatetimeLocal(value: Date): string {
  return `${value.getFullYear()}-${pad2(value.getMonth() + 1)}-${pad2(value.getDate())}T${pad2(value.getHours())}:${pad2(value.getMinutes())}`;
}

function defaultDateRange(): { from: string; to: string } {
  const now = new Date();
  const start = new Date(now);
  start.setHours(0, 0, 0, 0);
  return { from: toDatetimeLocal(start), to: toDatetimeLocal(now) };
}

function localInputToUtcIso(value: string): string {
  return new Date(value).toISOString();
}

function formatWhen(value: string | null): string {
  if (!value) return "";
  const hasZone = /Z$/i.test(value) || /[+-]\d{2}:\d{2}$/.test(value);
  const d = new Date(hasZone ? value : `${value}Z`);
  if (Number.isNaN(d.getTime())) return "";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(d);
}

function titleForLabel(slug: string): string {
  return CLASSIFY_LABEL_TITLES[slug as keyof typeof CLASSIFY_LABEL_TITLES] ?? slug;
}

function senderName(sender: string): string {
  const match = sender.match(/^"?([^"<]+)"?\s*</);
  if (match?.[1]) return match[1].trim();
  return sender || "Unknown";
}

function initialsFrom(text: string): string {
  const clean = text.replace(/@.*/, "").replace(/[^a-zA-Z0-9 ]/g, " ").trim();
  const parts = clean.split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

const OUTCOME_PAGE_SIZE = 20;
const CHART_LABELS = CLASSIFY_LABELS;
const OUTCOME_CATEGORIES: { key: OutcomeLabel; title: string }[] = [
  { key: "screening", title: "Screening" },
  { key: "interview", title: "Interview" },
  { key: "rejected", title: "Rejected" },
];

function tsvCell(value: string): string {
  return value.replace(/[\t\r\n]+/g, " ");
}

function OutcomeTable({ rows }: { rows: OutcomeEntry[] }) {
  return (
    <section className="outcome-block">
      {rows.length === 0 ? (
        <p className="hint">None in this date range.</p>
      ) : (
        <div className="settings-table-wrap outcome-table">
          <table className="settings-table">
            <thead>
              <tr>
                <th>Company</th>
                <th>Role</th>
                <th>Date</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={`${index}-${row.received_at ?? ""}-${row.subject}`}>
                  <td data-label="Company">{row.company || row.subject || "—"}</td>
                  <td data-label="Role">{row.role || "—"}</td>
                  <td data-label="Date">{formatWhen(row.received_at) || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export default function SettingsPage({
  section,
  onSectionChange,
  onClose,
  themePref,
  onThemeChange,
  viewMode,
  onViewModeChange,
  inboxType,
  onInboxTypeChange,
  fontFamily,
  onFontFamilyChange,
  fontSize,
  onFontSizeChange,
  mailboxes,
  unusedTraining,
  updatingPrompt,
  onUpdatePrompt,
  initialMailboxId = null,
}: {
  section: SettingsSection;
  onSectionChange: (section: SettingsSection) => void;
  onClose: () => void;
  themePref: ThemePref;
  onThemeChange: (pref: ThemePref) => void;
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
  inboxType: InboxType;
  onInboxTypeChange: (type: InboxType) => void;
  fontFamily: FontFamily;
  onFontFamilyChange: (font: FontFamily) => void;
  fontSize: FontSize;
  onFontSizeChange: (size: FontSize) => void;
  mailboxes: Mailbox[];
  unusedTraining: number;
  updatingPrompt: boolean;
  onUpdatePrompt: () => Promise<void> | void;
  initialMailboxId?: number | null;
}) {
  const [promptStatus, setPromptStatus] = useState<ClassifyPromptStatus | null>(null);
  const [training, setTraining] = useState<ClassifyTrainingExample[]>([]);
  const [trainingTotal, setTrainingTotal] = useState(0);
  const [trainingPage, setTrainingPage] = useState(0);
  const [trainingError, setTrainingError] = useState<string | null>(null);
  const [trainingLoading, setTrainingLoading] = useState(section === "training");

  const dateDefaults = useMemo(() => defaultDateRange(), []);
  const [statsMailboxId, setStatsMailboxId] = useState<number | "all">(
    initialMailboxId ?? "all"
  );
  const [dateFrom, setDateFrom] = useState(dateDefaults.from);
  const [dateTo, setDateTo] = useState(dateDefaults.to);
  const [stats, setStats] = useState<MailboxLabelStats | null>(null);
  const [timelines, setTimelines] = useState<LabelTimeline[]>([]);
  const [outcomeLabel, setOutcomeLabel] = useState<OutcomeLabel>("screening");
  const [outcomePage, setOutcomePage] = useState(0);
  const [outcomeItems, setOutcomeItems] = useState<OutcomeEntry[]>([]);
  const [outcomeTotal, setOutcomeTotal] = useState(0);
  const [statsError, setStatsError] = useState<string | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);
  const [copying, setCopying] = useState(false);
  const [copyNote, setCopyNote] = useState<string | null>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    if (section !== "training") return;
    let cancelled = false;
    setTrainingLoading(true);
    setTrainingError(null);
    Promise.all([
      fetchClassifyTraining({ limit: TRAINING_PAGE_SIZE, offset: trainingPage * TRAINING_PAGE_SIZE }),
      fetchClassifyPromptStatus(),
    ])
      .then(([page, status]) => {
        if (cancelled) return;
        setPromptStatus(status);
        setTrainingTotal(page.total);
        const lastPage = Math.max(0, Math.ceil(page.total / TRAINING_PAGE_SIZE) - 1);
        if (trainingPage > lastPage) {
          setTrainingPage(lastPage);
          return;
        }
        setTraining(page.items);
      })
      .catch((err) => {
        if (!cancelled) {
          setTrainingError(err instanceof Error ? err.message : "Failed to load training data");
        }
      })
      .finally(() => {
        if (!cancelled) setTrainingLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [section, unusedTraining, trainingPage]);

  async function loadStats(
    event?: FormEvent,
    page = outcomePage,
    label: OutcomeLabel = outcomeLabel,
    mailboxId: number | "all" = statsMailboxId
  ) {
    event?.preventDefault();
    if (dateFrom > dateTo) {
      setStatsError("From must be on or before To");
      return;
    }
    const fromIso = localInputToUtcIso(dateFrom);
    const toIso = localInputToUtcIso(dateTo);
    setStatsLoading(true);
    setStatsError(null);
    setCopyNote(null);
    try {
      if (mailboxId === "all") {
        const result = await fetchMailboxLabelStats("all", fromIso, toIso);
        setStats(result);
        setTimelines([]);
        setOutcomeItems([]);
        setOutcomeTotal(0);
        return;
      }
      const [result, lineResults, outcomeResult] = await Promise.all([
        fetchMailboxLabelStats(mailboxId, fromIso, toIso),
        Promise.all(CHART_LABELS.map((lineLabel) => fetchMailboxLabelTimeline(mailboxId, lineLabel, fromIso, toIso))),
        label === "applied"
          ? Promise.resolve(null)
          : fetchMailboxOutcomes(mailboxId, fromIso, toIso, {
              label,
              limit: OUTCOME_PAGE_SIZE,
              offset: page * OUTCOME_PAGE_SIZE,
            }),
      ]);
      setStats(result);
      setTimelines(lineResults);
      setOutcomeItems(outcomeResult?.items ?? []);
      setOutcomeTotal(outcomeResult?.total ?? 0);
    } catch (err) {
      setStats(null);
      setTimelines([]);
      setOutcomeItems([]);
      setOutcomeTotal(0);
      setStatsError(err instanceof Error ? err.message : "Failed to load statistics");
    } finally {
      setStatsLoading(false);
    }
  }

  function selectOutcome(label: OutcomeLabel) {
    setOutcomeLabel(label);
    setOutcomePage(0);
    setOutcomeItems([]);
    setOutcomeTotal(0);
    void loadStats(undefined, 0, label);
  }

  async function copyOutcomeResults() {
    if (statsMailboxId === "all" || outcomeLabel === "applied") return;
    setCopying(true);
    setCopyNote(null);
    try {
      const fromIso = localInputToUtcIso(dateFrom);
      const toIso = localInputToUtcIso(dateTo);
      const rows: OutcomeEntry[] = [];
      let offset = 0;
      let total = 0;
      do {
        const page = await fetchMailboxOutcomes(statsMailboxId, fromIso, toIso, {
          label: outcomeLabel,
          limit: 100,
          offset,
        });
        total = page.total;
        rows.push(...page.items);
        offset += page.items.length;
        if (page.items.length === 0) break;
      } while (rows.length < total);
      const lines = [
        "Company\tRole\tDate\tSubject",
        ...rows.map((row) =>
          [row.company, row.role, formatWhen(row.received_at), row.subject].map(tsvCell).join("\t")
        ),
      ];
      await navigator.clipboard.writeText(lines.join("\n"));
      setCopyNote(`Copied ${rows.length}`);
    } catch (err) {
      setCopyNote(err instanceof Error ? err.message : "Could not copy");
    } finally {
      setCopying(false);
    }
  }

  useEffect(() => {
    if (section !== "statistics") return;
    void loadStats();
    // Load once when opening Statistics.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [section]);

  async function handleUpdatePrompt() {
    await onUpdatePrompt();
  }

  const navItems: { id: SettingsSection; label: string }[] = [
    { id: "appearance", label: "Appearance" },
    { id: "training", label: "Training" },
    { id: "statistics", label: "Statistics" },
  ];

  return (
    <div className="settings-overlay" role="dialog" aria-modal="true" aria-labelledby="settings-title">
      <div className="settings-shell">
        <header className="settings-top">
          <h2 id="settings-title">Settings</h2>
          <button type="button" className="action-btn" onClick={onClose}>
            Back to inbox
          </button>
        </header>
        <div className="settings-body">
          <nav className="settings-nav" aria-label="Settings sections">
            {navItems.map((item) => (
              <button
                key={item.id}
                type="button"
                className={section === item.id ? "settings-nav-btn active" : "settings-nav-btn"}
                onClick={() => {
                  if (item.id === "training") setTrainingLoading(true);
                  onSectionChange(item.id);
                }}
              >
                {item.label}
                {item.id === "training" && unusedTraining > 0 ? (
                  <span className="count-pill">{unusedTraining}</span>
                ) : null}
              </button>
            ))}
          </nav>
          <div className="settings-content">
            {section === "appearance" && (
              <div className="settings-panel">
                <section className="settings-block">
                  <h3>View mode</h3>
                  <p className="settings-help">How the inbox message list is shown.</p>
                  <div className="seg-control" role="radiogroup" aria-label="View mode">
                    {VIEW_MODES.map((mode) => (
                      <button
                        key={mode}
                        type="button"
                        role="radio"
                        aria-checked={viewMode === mode}
                        className={viewMode === mode ? "seg-btn active" : "seg-btn"}
                        onClick={() => onViewModeChange(mode)}
                      >
                        {mode === "list" ? "List" : "Card"}
                      </button>
                    ))}
                  </div>
                </section>
                <section className="settings-block">
                  <h3>Inbox type</h3>
                  <p className="settings-help">Order of messages in the inbox list.</p>
                  <div className="seg-control" role="radiogroup" aria-label="Inbox type">
                    {INBOX_TYPES.map((type) => (
                      <button
                        key={type}
                        type="button"
                        role="radio"
                        aria-checked={inboxType === type}
                        className={inboxType === type ? "seg-btn active" : "seg-btn"}
                        onClick={() => onInboxTypeChange(type)}
                      >
                        {type === "default" ? "Default" : "Unread first"}
                      </button>
                    ))}
                  </div>
                </section>
                <section className="settings-block">
                  <h3>Theme</h3>
                  <p className="settings-help">Color scheme for the app.</p>
                  <div className="seg-control" role="radiogroup" aria-label="Theme">
                    {(["system", "dark", "light"] as ThemePref[]).map((item) => (
                      <button
                        key={item}
                        type="button"
                        role="radio"
                        aria-checked={themePref === item}
                        className={themePref === item ? "seg-btn active" : "seg-btn"}
                        onClick={() => onThemeChange(item)}
                      >
                        {item === "system" ? "System" : item === "dark" ? "Dark" : "Light"}
                      </button>
                    ))}
                  </div>
                </section>
                <section className="settings-block">
                  <h3>Font</h3>
                  <p className="settings-help">Typeface and size used across the app.</p>
                  <label className="settings-field">
                    Family
                    <select
                      value={fontFamily}
                      onChange={(event) => onFontFamilyChange(event.target.value as FontFamily)}
                    >
                      {FONT_FAMILIES.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="seg-control" role="radiogroup" aria-label="Font size">
                    {FONT_SIZES.map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        role="radio"
                        aria-checked={fontSize === item.id}
                        className={fontSize === item.id ? "seg-btn active" : "seg-btn"}
                        onClick={() => onFontSizeChange(item.id)}
                      >
                        {item.label}
                      </button>
                    ))}
                  </div>
                </section>
              </div>
            )}

            {section === "training" && (
              <div className="settings-panel">
                <section className="settings-block">
                  <h3>Classification training</h3>
                  <p className="settings-help">
                    Corrections saved from the reader. Unused examples can update the classify prompt.
                  </p>
                  <div className="settings-status-row">
                    <p>
                      {unusedTraining > 0
                        ? `${unusedTraining} unused example${unusedTraining === 1 ? "" : "s"} ready`
                        : "No unused training examples"}
                      {trainingTotal > 0 ? ` · ${trainingTotal} total` : ""}
                    </p>
                    {promptStatus?.updated_at ? (
                      <p className="settings-help">
                        Prompt v{promptStatus.active_version_id ?? "—"}
                        {promptStatus.active_source ? ` · ${promptStatus.active_source}` : ""}
                        {` · updated ${formatWhen(promptStatus.updated_at)}`}
                      </p>
                    ) : null}
                    <button
                      type="button"
                      className={updatingPrompt ? "action-btn busy" : "action-btn"}
                      disabled={updatingPrompt || unusedTraining <= 0}
                      onClick={() => void handleUpdatePrompt()}
                    >
                      {updatingPrompt ? (
                        <>
                          <span className="spinner" aria-hidden="true" />
                          Updating prompt
                        </>
                      ) : unusedTraining > 0 ? (
                        `Update prompt (${unusedTraining})`
                      ) : (
                        "Update prompt"
                      )}
                    </button>
                  </div>
                  {trainingError && <p className="error">{trainingError}</p>}
                  {trainingLoading && <p className="hint">Loading training data…</p>}
                  {!trainingLoading && training.length === 0 && !trainingError && (
                    <p className="hint">Correct a category and save it as training data first.</p>
                  )}
                  {training.length > 0 && (
                    <div className="training-cards">
                      {training.map((row) => {
                        const used = row.used_in_prompt_version_id != null;
                        const from = senderName(row.sender);
                        return (
                          <article key={row.id} className="training-card">
                            <span className={`avatar soft label-${row.corrected_label}`}>
                              {initialsFrom(from)}
                            </span>
                            <span className="msg-body">
                              <span className="msg-top">
                                <span className="msg-from">
                                  <strong>{from}</strong>
                                </span>
                                <time className="msg-time">{formatWhen(row.created_at)}</time>
                              </span>
                              <span className="msg-subject">{row.subject || "(no subject)"}</span>
                              {row.snippet ? <span className="msg-snippet">{row.snippet}</span> : null}
                              <span className="msg-card-meta">
                                <span className={`label list-label label-${row.previous_label}`}>
                                  {titleForLabel(row.previous_label)}
                                </span>
                                <span className="training-arrow" aria-hidden="true">
                                  →
                                </span>
                                <span className={`label list-label label-${row.corrected_label}`}>
                                  {titleForLabel(row.corrected_label)}
                                </span>
                                <span className={used ? "read-pill" : "new-pill"}>
                                  {used ? "Used" : "Unused"}
                                </span>
                              </span>
                            </span>
                          </article>
                        );
                      })}
                    </div>
                  )}
                  {trainingTotal > TRAINING_PAGE_SIZE && (
                    <div className="training-pager">
                      <button
                        type="button"
                        className="action-btn"
                        disabled={trainingLoading || trainingPage === 0}
                        onClick={() => setTrainingPage((page) => Math.max(0, page - 1))}
                      >
                        Previous
                      </button>
                      <span>
                        Page {trainingPage + 1} of {Math.ceil(trainingTotal / TRAINING_PAGE_SIZE)} · {trainingTotal}
                      </span>
                      <button
                        type="button"
                        className="action-btn"
                        disabled={
                          trainingLoading ||
                          trainingPage >= Math.ceil(trainingTotal / TRAINING_PAGE_SIZE) - 1
                        }
                        onClick={() => setTrainingPage((page) => page + 1)}
                      >
                        Next
                      </button>
                    </div>
                  )}
                </section>
              </div>
            )}

            {section === "statistics" && (
              <div className="settings-panel">
                <section className="settings-block">
                  <h3>Category statistics</h3>
                  <p className="settings-help">
                    Counts from the start of today through now. All accounts shows every mailbox.
                    One account shows every category on the pie and the line chart. Company and role are listed for screening, interview, and rejected.
                  </p>
                  <form
                    className="stats-form"
                    onSubmit={(event) => {
                      setOutcomePage(0);
                      void loadStats(event, 0);
                    }}
                  >
                    <AccountSelect
                      value={statsMailboxId}
                      mailboxes={mailboxes}
                      onChange={(value) => {
                        setStatsMailboxId(value);
                        setOutcomePage(0);
                        setStats(null);
                        setTimelines([]);
                        setOutcomeItems([]);
                        setOutcomeTotal(0);
                        void loadStats(undefined, 0, outcomeLabel, value);
                      }}
                    />
                    <DateTimeField label="From" value={dateFrom} onChange={setDateFrom} />
                    <DateTimeField label="To" value={dateTo} onChange={setDateTo} />
                    <button type="submit" className="action-btn" disabled={statsLoading}>
                      {statsLoading ? "Loading…" : "Search"}
                    </button>
                  </form>
                  {statsError && <p className="error">{statsError}</p>}
                  {stats && stats.total === 0 && !statsError && (
                    <p className="hint">No emails in this date range.</p>
                  )}
                  {stats && (
                    <div className="stats-chart-scroll">
                      <LabelBarChart counts={stats.label_counts} total={stats.total} />
                    </div>
                  )}
                  {stats && statsMailboxId !== "all" && (
                    <div className="stats-visuals stats-account">
                      <LabelPieChart
                        counts={stats.label_counts}
                        active={outcomeLabel}
                        onSelect={selectOutcome}
                      />
                      <CategoryLineChart series={timelines} />
                    </div>
                  )}
                  {statsMailboxId !== "all" && stats && (
                    <section className="outcome-block">
                      <div className="outcome-toolbar">
                        <div className="folder-badges" role="tablist" aria-label="Outcome category">
                          {OUTCOME_CATEGORIES.map((item) => (
                            <button
                              key={item.key}
                              type="button"
                              className={outcomeLabel === item.key ? "folder-badge active" : "folder-badge"}
                              onClick={() => selectOutcome(item.key)}
                            >
                              {item.title}
                              {outcomeLabel === item.key ? (
                                <span className="count-pill">{outcomeTotal}</span>
                              ) : null}
                            </button>
                          ))}
                        </div>
                        {outcomeLabel !== "applied" && (
                          <button
                            type="button"
                            className="action-btn"
                            disabled={copying || outcomeTotal === 0}
                            onClick={() => void copyOutcomeResults()}
                          >
                            {copying ? "Copying…" : "Copy"}
                          </button>
                        )}
                      </div>
                      {outcomeLabel === "applied" ? (
                        <p className="hint">Company and role are not listed for Applied.</p>
                      ) : (
                        <>
                          {copyNote && <p className="hint">{copyNote}</p>}
                          <OutcomeTable rows={outcomeItems} />
                          {outcomeTotal > OUTCOME_PAGE_SIZE && (
                            <div className="training-pager">
                              <button
                                type="button"
                                className="action-btn"
                                disabled={statsLoading || outcomePage === 0}
                                onClick={() => {
                                  const next = Math.max(0, outcomePage - 1);
                                  setOutcomePage(next);
                                  void loadStats(undefined, next);
                                }}
                              >
                                Previous
                              </button>
                              <span>
                                Page {outcomePage + 1} of {Math.ceil(outcomeTotal / OUTCOME_PAGE_SIZE)} ·{" "}
                                {outcomeTotal}
                              </span>
                              <button
                                type="button"
                                className="action-btn"
                                disabled={
                                  statsLoading ||
                                  outcomePage >= Math.ceil(outcomeTotal / OUTCOME_PAGE_SIZE) - 1
                                }
                                onClick={() => {
                                  const next = outcomePage + 1;
                                  setOutcomePage(next);
                                  void loadStats(undefined, next);
                                }}
                              >
                                Next
                              </button>
                            </div>
                          )}
                        </>
                      )}
                    </section>
                  )}
                </section>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
