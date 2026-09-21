import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  fetchClassifyPromptStatus,
  fetchClassifyTraining,
  fetchMailboxLabelStats,
  type ClassifyPromptStatus,
  type ClassifyTrainingExample,
  type Mailbox,
  type MailboxLabelStats,
} from "../api";
import { CLASSIFY_LABEL_TITLES } from "../labels";
import {
  FONT_FAMILIES,
  FONT_SIZES,
  VIEW_MODES,
  type FontFamily,
  type FontSize,
  type ViewMode,
} from "../prefs";
import type { ThemePref } from "../theme";
import LabelBarChart from "../components/LabelBarChart";

export type SettingsSection = "appearance" | "training" | "statistics";

function localIsoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function defaultDateRange(): { from: string; to: string } {
  const to = new Date();
  const from = new Date();
  from.setDate(from.getDate() - 29);
  return { from: localIsoDate(from), to: localIsoDate(to) };
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

export default function SettingsPage({
  section,
  onSectionChange,
  onClose,
  themePref,
  onThemeChange,
  viewMode,
  onViewModeChange,
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
  const [trainingError, setTrainingError] = useState<string | null>(null);
  const [trainingLoading, setTrainingLoading] = useState(section === "training");

  const dateDefaults = useMemo(() => defaultDateRange(), []);
  const [statsMailboxId, setStatsMailboxId] = useState<number | "">(
    initialMailboxId ?? mailboxes[0]?.id ?? ""
  );
  const [dateFrom, setDateFrom] = useState(dateDefaults.from);
  const [dateTo, setDateTo] = useState(dateDefaults.to);
  const [stats, setStats] = useState<MailboxLabelStats | null>(null);
  const [statsError, setStatsError] = useState<string | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);

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
    Promise.all([fetchClassifyTraining(), fetchClassifyPromptStatus()])
      .then(([page, status]) => {
        if (cancelled) return;
        setTraining(page.items);
        setTrainingTotal(page.total);
        setPromptStatus(status);
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
  }, [section, unusedTraining]);

  async function loadStats(event?: FormEvent) {
    event?.preventDefault();
    if (statsMailboxId === "") {
      setStatsError("Select an account");
      setStats(null);
      return;
    }
    if (dateFrom > dateTo) {
      setStatsError("From date must be on or before To date");
      return;
    }
    setStatsLoading(true);
    setStatsError(null);
    try {
      const result = await fetchMailboxLabelStats(Number(statsMailboxId), dateFrom, dateTo);
      setStats(result);
    } catch (err) {
      setStats(null);
      setStatsError(err instanceof Error ? err.message : "Failed to load statistics");
    } finally {
      setStatsLoading(false);
    }
  }

  useEffect(() => {
    if (section !== "statistics") return;
    if (statsMailboxId === "") return;
    void loadStats();
    // Load once when opening Statistics with a mailbox selected.
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
                        {mode === "list" ? "List" : mode === "table" ? "Table" : "Card"}
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
                    <div className="settings-table-wrap">
                      <table className="settings-table">
                        <thead>
                          <tr>
                            <th>From</th>
                            <th>Subject</th>
                            <th>Previous</th>
                            <th>Corrected</th>
                            <th>Status</th>
                            <th>Date</th>
                          </tr>
                        </thead>
                        <tbody>
                          {training.map((row) => {
                            const used = row.used_in_prompt_version_id != null;
                            return (
                              <tr key={row.id}>
                                <td>{row.sender || "—"}</td>
                                <td>{row.subject || "(no subject)"}</td>
                                <td>
                                  <span className={`label list-label label-${row.previous_label}`}>
                                    {titleForLabel(row.previous_label)}
                                  </span>
                                </td>
                                <td>
                                  <span className={`label list-label label-${row.corrected_label}`}>
                                    {titleForLabel(row.corrected_label)}
                                  </span>
                                </td>
                                <td>
                                  <span className={used ? "read-pill" : "new-pill"}>
                                    {used ? "Used" : "Unused"}
                                  </span>
                                </td>
                                <td>{formatWhen(row.created_at)}</td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
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
                    Counts of classification labels for one account in a date range.
                  </p>
                  <form className="stats-form" onSubmit={(event) => void loadStats(event)}>
                    <label className="settings-field">
                      Account
                      <select
                        value={statsMailboxId === "" ? "" : String(statsMailboxId)}
                        onChange={(event) =>
                          setStatsMailboxId(event.target.value ? Number(event.target.value) : "")
                        }
                      >
                        {mailboxes.length === 0 && <option value="">No accounts</option>}
                        {mailboxes.map((box) => (
                          <option key={box.id} value={box.id}>
                            {box.email_address}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="settings-field">
                      From
                      <input
                        type="date"
                        value={dateFrom}
                        onChange={(event) => setDateFrom(event.target.value)}
                        required
                      />
                    </label>
                    <label className="settings-field">
                      To
                      <input
                        type="date"
                        value={dateTo}
                        onChange={(event) => setDateTo(event.target.value)}
                        required
                      />
                    </label>
                    <button type="submit" className="action-btn" disabled={statsLoading || mailboxes.length === 0}>
                      {statsLoading ? "Loading…" : "Search"}
                    </button>
                  </form>
                  {statsError && <p className="error">{statsError}</p>}
                  {!mailboxes.length && <p className="hint">Add an account to see statistics.</p>}
                  {stats && stats.total === 0 && !statsError && (
                    <p className="hint">No emails in this date range for the selected account.</p>
                  )}
                  {stats && stats.total > 0 && (
                    <LabelBarChart counts={stats.label_counts} total={stats.total} />
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
