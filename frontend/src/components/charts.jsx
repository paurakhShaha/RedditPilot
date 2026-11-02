import React from "react";
import { compactNumber } from "../utils.js";

const PAD = { top: 16, right: 10, bottom: 28, left: 38 };
const WIDTH = 640;

export function ChartEmpty({ height = 180, message = "No data yet" }) {
  return (
    <div
      className="empty"
      style={{ minHeight: height, padding: "24px 12px", border: "1px dashed var(--line-soft)", borderRadius: 8 }}
    >
      <p className="empty-text" style={{ fontSize: 11.5 }}>{message}</p>
    </div>
  );
}

export function SparkBars({ values = [], width = 76, height = 30, accentLast = true }) {
  const items = values.slice(-10);
  if (!items.length) return <svg width={width} height={height} className="spark-svg" />;
  const max = Math.max(...items, 1);
  const gap = 2;
  const barWidth = (width - gap * (items.length - 1)) / items.length;
  return (
    <svg width={width} height={height} className="spark-svg" aria-hidden="true">
      {items.map((value, index) => {
        const h = Math.max(2, (value / max) * (height - 2));
        return (
          <rect
            key={index}
            x={index * (barWidth + gap)}
            y={height - h}
            width={barWidth}
            height={h}
            rx={1.5}
            className={`spark-bar ${accentLast && index === items.length - 1 ? "on" : ""}`}
          />
        );
      })}
    </svg>
  );
}

export function BarChart({ data = [], labelKey = "label", valueKey = "value", height = 220, unit = "", highlightLast = false, format = compactNumber }) {
  const values = data.map((row) => Number(row[valueKey] || 0));
  if (!data.length) return <ChartEmpty height={height} />;
  const max = Math.max(...values, 1);
  const innerW = WIDTH - PAD.left - PAD.right;
  const innerH = height - PAD.top - PAD.bottom;
  const slot = innerW / data.length;
  const barW = Math.max(4, Math.min(46, slot * 0.56));
  const ticks = 4;

  return (
    <div className="chart-wrap">
      <svg className="chart-svg" viewBox={`0 0 ${WIDTH} ${height}`} role="img" aria-label="Bar chart">
        <g className="chart-grid">
          {Array.from({ length: ticks + 1 }).map((_, index) => {
            const y = PAD.top + (innerH / ticks) * index;
            const value = Math.round((max / ticks) * (ticks - index));
            return (
              <g key={index}>
                <line x1={PAD.left} x2={WIDTH - PAD.right} y1={y} y2={y} />
                <text x={PAD.left - 8} y={y + 3} textAnchor="end" className="chart-axis">
                  {format(value)}
                </text>
              </g>
            );
          })}
        </g>
        {data.map((row, index) => {
          const value = Number(row[valueKey] || 0);
          const h = Math.max(value > 0 ? 3 : 1, (value / max) * innerH);
          const x = PAD.left + slot * index + (slot - barW) / 2;
          const y = PAD.top + innerH - h;
          const isLast = highlightLast && index === data.length - 1;
          return (
            <g key={index}>
              <rect
                x={x}
                y={y}
                width={barW}
                height={h}
                rx={2}
                className={`chart-bar ${isLast ? "accent" : ""}`}
                style={isLast ? { fill: "var(--accent)" } : undefined}
              >
                <title>{`${row[labelKey]}: ${value}${unit ? ` ${unit}` : ""}`}</title>
              </rect>
              {(data.length <= 10 || index % 2 === 0) && (
                <text x={x + barW / 2} y={height - 8} textAnchor="middle" className="chart-axis">
                  {row[labelKey]}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export function LineChart({ data = [], labelKey = "label", series = [], height = 230, showLegend = true }) {
  if (!data.length) return <ChartEmpty height={height} />;
  const innerW = WIDTH - PAD.left - PAD.right;
  const innerH = height - PAD.top - PAD.bottom;
  const max = Math.max(1, ...data.flatMap((row) => series.map((item) => Number(row[item.key] || 0))));
  const stepX = data.length > 1 ? innerW / (data.length - 1) : innerW;
  const yFor = (value) => PAD.top + innerH - (Number(value || 0) / max) * innerH;
  const xFor = (index) => PAD.left + (data.length > 1 ? stepX * index : innerW / 2);
  const ticks = 4;

  const linePath = (key) => data.map((row, index) => `${index === 0 ? "M" : "L"}${xFor(index).toFixed(1)},${yFor(row[key]).toFixed(1)}`).join(" ");
  const areaPath = (key) => {
    const line = linePath(key);
    return `${line} L${xFor(data.length - 1).toFixed(1)},${PAD.top + innerH} L${xFor(0).toFixed(1)},${PAD.top + innerH} Z`;
  };

  return (
    <div className="chart-wrap">
      <svg className="chart-svg" viewBox={`0 0 ${WIDTH} ${height}`} role="img" aria-label="Line chart">
        <defs>
          {series.map((item) => (
            <linearGradient key={item.key} id={`gradient-${item.key}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={item.color} stopOpacity=".28" />
              <stop offset="100%" stopColor={item.color} stopOpacity="0" />
            </linearGradient>
          ))}
        </defs>
        <g className="chart-grid">
          {Array.from({ length: ticks + 1 }).map((_, index) => {
            const y = PAD.top + (innerH / ticks) * index;
            const value = Math.round((max / ticks) * (ticks - index));
            return (
              <g key={index}>
                <line x1={PAD.left} x2={WIDTH - PAD.right} y1={y} y2={y} />
                <text x={PAD.left - 8} y={y + 3} textAnchor="end" className="chart-axis">{compactNumber(value)}</text>
              </g>
            );
          })}
        </g>
        {series.map((item) => (
          <path key={`area-${item.key}`} d={areaPath(item.key)} fill={`url(#gradient-${item.key})`} stroke="none" />
        ))}
        {series.map((item) => (
          <path key={`line-${item.key}`} d={linePath(item.key)} className="chart-line" style={{ stroke: item.color }} />
        ))}
        {data.map((row, index) => {
          if (data.length > 16 && index % 2 !== 0) return null;
          return (
            <g key={index}>
              {series.map((item) => (
                <circle
                  key={item.key}
                  cx={xFor(index)}
                  cy={yFor(row[item.key])}
                  r={data.length > 16 ? 2.2 : 3}
                  className="chart-dot"
                  style={{ fill: item.color }}
                >
                  <title>{`${row[labelKey]} · ${item.label}: ${Number(row[item.key] || 0)}`}</title>
                </circle>
              ))}
            </g>
          );
        })}
        {data.map((row, index) => {
          const show = data.length <= 7 || index === 0 || index === data.length - 1 || index % Math.ceil(data.length / 5) === 0;
          if (!show) return null;
          return (
            <text key={`label-${index}`} x={xFor(index)} y={height - 8} textAnchor="middle" className="chart-axis">
              {row[labelKey]}
            </text>
          );
        })}
      </svg>
      {showLegend && series.length > 0 && (
        <div className="chart-legend" style={{ marginTop: 10 }}>
          {series.map((item) => (
            <span key={item.key}><i style={{ background: item.color }} />{item.label}</span>
          ))}
        </div>
      )}
    </div>
  );
}

export function HBarList({ rows = [], labelKey = "label", valueKey = "value", color = "var(--accent)", format = compactNumber, empty = "No data yet." }) {
  if (!rows.length) return <p className="field-hint">{empty}</p>;
  const max = Math.max(...rows.map((row) => Number(row[valueKey] || 0)), 1);
  return (
    <div className="stack-sm">
      {rows.map((row, index) => {
        const value = Number(row[valueKey] || 0);
        return (
          <div key={`${row[labelKey]}-${index}`}>
            <div className="row-between" style={{ marginBottom: 4 }}>
              <span className="truncate" style={{ fontSize: 11.5, color: "var(--text-soft)", maxWidth: "70%" }}>{row[labelKey]}</span>
              <span className="mono" style={{ color: "var(--text-mid)" }}>{format(value)}</span>
            </div>
            <div className="meter" style={{ height: 4 }}>
              <div className="meter-fill" style={{ width: `${Math.max(2, (value / max) * 100)}%`, background: color }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function Donut({ value = 0, max = 100, size = 78, stroke = 7, color = "var(--accent)", label }) {
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const percent = max > 0 ? Math.min(1, value / max) : 0;
  return (
    <div style={{ position: "relative", width: size, height: size, flex: "none" }}>
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }} aria-hidden="true">
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="#24282f" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${circumference * percent} ${circumference}`}
        />
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", textAlign: "center" }}>
        <div>
          <div style={{ fontFamily: "var(--serif)", fontSize: 20, lineHeight: 1 }}>{Math.round(percent * 100)}%</div>
          {label && <div style={{ fontSize: 8, color: "var(--muted)", marginTop: 2 }}>{label}</div>}
        </div>
      </div>
    </div>
  );
}
