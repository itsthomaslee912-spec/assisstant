import type { EmailLabel, OutcomeLabel } from "../api";
import { CLASSIFY_LABELS, CLASSIFY_LABEL_TITLES, LABEL_BAR_COLORS } from "../labels";

const OUTCOME_LABELS = new Set<EmailLabel>(["applied", "rejected", "screening", "interview"]);

export default function LabelPieChart({
  counts,
  active,
  onSelect,
}: {
  counts: Record<string, number>;
  active: OutcomeLabel;
  onSelect: (label: OutcomeLabel) => void;
}) {
  const slices = CLASSIFY_LABELS.map((key) => ({
    key,
    value: counts[key] ?? 0,
    color: LABEL_BAR_COLORS[key],
    title: CLASSIFY_LABEL_TITLES[key],
  }));
  const total = slices.reduce((sum, slice) => sum + slice.value, 0);
  let cursor = 0;
  const gradient =
    total === 0
      ? "var(--bg-hover)"
      : `conic-gradient(${slices
          .map((slice) => {
            const start = (cursor / total) * 100;
            cursor += slice.value;
            const end = (cursor / total) * 100;
            return `${slice.color} ${start}% ${end}%`;
          })
          .join(", ")})`;

  return (
    <div className="stats-pie-block stats-card">
      <h4>All categories</h4>
      <div className="stats-pie-row">
        <div className="stats-donut" style={{ background: gradient }} role="img" aria-label="All category counts">
          <div className="stats-donut-hole">
            <strong>{total}</strong>
            <span>total</span>
          </div>
        </div>
        <ul className="stats-pie-legend">
          {slices.map((slice) => (
            <li key={slice.key} className={slice.key === active ? "active" : undefined}>
              {OUTCOME_LABELS.has(slice.key) ? (
                <button
                  type="button"
                  className="stats-pie-pick"
                  onClick={() => onSelect(slice.key as OutcomeLabel)}
                >
                  <span className="stats-pie-swatch" style={{ background: slice.color }} />
                  <span>{slice.title}</span>
                  <strong>{slice.value}</strong>
                </button>
              ) : (
                <span className="stats-pie-pick">
                  <span className="stats-pie-swatch" style={{ background: slice.color }} />
                  <span>{slice.title}</span>
                  <strong>{slice.value}</strong>
                </span>
              )}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
