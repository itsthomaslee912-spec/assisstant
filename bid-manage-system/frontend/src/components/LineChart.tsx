import { useEffect, useRef, useState } from "react";
import type { Point } from "../types";

export default function LineChart({ data, color = "#7c8cff" }: { data: Point[]; color?: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(760);
  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;
    const observer = new ResizeObserver(entries => setContainerWidth(entries[0].contentRect.width));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const width = Math.max(containerWidth, data.length * 36, 620), height = 230, padX = 34, padY = 28;
  const max = Math.max(1, ...data.map((item) => item.value));
  const step = data.length > 1 ? (width - padX * 2) / (data.length - 1) : 0;
  const points = data.map((item, index) => ({
    ...item,
    x: padX + index * step,
    y: height - padY - (item.value / max) * (height - padY * 2),
  }));
  const path = points.map((point, index) => `${index ? "L" : "M"}${point.x},${point.y}`).join(" ");
  return (
    <div className="chart-scroll" ref={containerRef}>
      <svg className="line-chart" viewBox={`0 0 ${width} ${height}`} style={{ width }} role="img" aria-label="Application activity line chart">
        <line x1={padX} y1={height - padY} x2={width - padX} y2={height - padY} className="chart-axis" />
        {points.length > 1 && <path d={`${path} L${points.at(-1)!.x},${height - padY} L${padX},${height - padY} Z`} fill={`${color}18`} />}
        <path d={path} fill="none" stroke={color} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
        {points.map((point) => <g key={`${point.label}-${point.x}`}>
          <circle cx={point.x} cy={point.y} r="4" fill={color} />
          <text x={point.x} y={point.y - 11} textAnchor="middle" className="chart-value">{point.value}</text>
          <text x={point.x} y={height - 7} textAnchor="middle" className="chart-label">{point.label}</text>
        </g>)}
      </svg>
    </div>
  );
}
