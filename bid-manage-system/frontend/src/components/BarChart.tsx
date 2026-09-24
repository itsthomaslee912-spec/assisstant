import { useEffect, useRef, useState } from "react";
import type { Point } from "../types";

export default function BarChart({ data, color = "#6d7cff" }: { data: Point[]; color?: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(760);
  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;
    const observer = new ResizeObserver(entries => setContainerWidth(entries[0].contentRect.width));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const width = Math.max(containerWidth, data.length * 62, 620), height = 230, padX = 34, padY = 30;
  const max = Math.max(1, ...data.map(item => item.value));
  const slot = (width - padX * 2) / Math.max(1, data.length);
  const barWidth = Math.min(34, slot * .58);
  return <div className="chart-scroll" ref={containerRef}>
    <svg className="line-chart bar-chart" viewBox={`0 0 ${width} ${height}`} style={{ width }} role="img" aria-label="Application activity bar chart">
      <line x1={padX} y1={height - padY} x2={width - padX} y2={height - padY} className="chart-axis" />
      {data.map((item, index) => {
        const barHeight = item.value / max * (height - padY * 2);
        const x = padX + index * slot + (slot - barWidth) / 2;
        const y = height - padY - barHeight;
        return <g key={`${item.label}-${index}`}>
          <rect x={x} y={y} width={barWidth} height={Math.max(2, barHeight)} rx="6" fill={color} />
          <text x={x + barWidth / 2} y={y - 8} textAnchor="middle" className="chart-value">{item.value}</text>
          <text x={x + barWidth / 2} y={height - 8} textAnchor="middle" className="chart-label">{item.label}</text>
        </g>;
      })}
    </svg>
  </div>;
}
