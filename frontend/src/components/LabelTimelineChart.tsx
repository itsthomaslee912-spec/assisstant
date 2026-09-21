import type { EmailLabel, LabelTimeline } from "../api";
import { CLASSIFY_LABEL_TITLES, LABEL_BAR_COLORS } from "../labels";

function bucketLabel(value: string, unit: LabelTimeline["bucket"]): string {
  const hasZone = /Z$/i.test(value) || /[+-]\d{2}:\d{2}$/.test(value);
  const date = new Date(hasZone ? value : `${value}Z`);
  if (Number.isNaN(date.getTime())) return value;
  if (unit === "hour") {
    return new Intl.DateTimeFormat(undefined, { hour: "numeric" }).format(date);
  }
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(date);
}

export default function LabelTimelineChart({ timeline }: { timeline: LabelTimeline }) {
  const max = Math.max(1, ...timeline.buckets.map((bucket) => bucket.count));
  const title = CLASSIFY_LABEL_TITLES[timeline.label as EmailLabel] ?? timeline.label;
  const color = LABEL_BAR_COLORS[timeline.label as EmailLabel] ?? "var(--muted)";

  return (
    <div className="stats-timeline">
      <h4>
        {title} by {timeline.bucket}
      </h4>
      <div className="stats-chart-scroll">
        <div className="timeline-bars" role="img" aria-label={`${title} counts by ${timeline.bucket}`}>
          {timeline.buckets.map((bucket) => (
            <div key={bucket.bucket} className="timeline-col" title={`${bucketLabel(bucket.bucket, timeline.bucket)}: ${bucket.count}`}>
              <span className="stats-bar-value">{bucket.count || ""}</span>
              <div className="stats-bar-track">
                <div
                  className="stats-bar-fill"
                  style={{ height: `${(bucket.count / max) * 100}%`, background: color }}
                />
              </div>
              <span className="stats-bar-name">{bucketLabel(bucket.bucket, timeline.bucket)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
