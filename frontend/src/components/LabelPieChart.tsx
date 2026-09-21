import type { EmailLabel } from "../api";
import { CLASSIFY_LABEL_TITLES, LABEL_BAR_COLORS } from "../labels";

const PIE_LABELS: EmailLabel[] = ["applied", "rejected", "screening", "interview"];

export default function LabelPieChart({ counts }: { counts: Record<string, number> }) {
  const slices = PIE_LABELS.map((key) => ({
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
    <div className="stats-pie-block">
      <h4>Applied, rejected, screening, interview</h4>
      <div className="stats-pie-row">
        <div
          className="stats-pie"
          style={{ background: gradient }}
          role="img"
          aria-label="Applied, rejected, screening, and interview counts"
        />
        <ul className="stats-pie-legend">
          {slices.map((slice) => (
            <li key={slice.key}>
              <span className="stats-pie-swatch" style={{ background: slice.color }} />
              <span>{slice.title}</span>
              <strong>{slice.value}</strong>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
