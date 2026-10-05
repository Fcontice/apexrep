"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  formatTrendValue,
  type TrendFormat,
  type TrendPoint,
} from "@/lib/trend";

type TrendChartProps = {
  /** Names the single series; used in the tooltip and for screen readers. */
  label: string;
  points: TrendPoint[];
  format: TrendFormat;
};

const tickDateFormat = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});

const tooltipDateFormat = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
  timeZone: "UTC",
});

const compactFormat = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 2,
});

const DAY_MS = 86_400_000;

/**
 * One tick per UTC midnight, so a date never appears twice on the axis. Returns
 * undefined for a span too short to hold two, where the axis shows times instead.
 */
function dayTicks(points: TrendPoint[]): number[] | undefined {
  const first: number = points[0].t;
  const last: number = points[points.length - 1].t;
  const ticks: number[] = [];
  for (let t = Math.ceil(first / DAY_MS) * DAY_MS; t <= last; t += DAY_MS) {
    ticks.push(t);
  }
  return ticks.length >= 2 ? ticks : undefined;
}

function formatAxisValue(value: number, format: TrendFormat): string {
  return format === "level" ? value.toFixed(1) : compactFormat.format(value);
}

type TrendTooltipProps = {
  active?: boolean;
  payload?: readonly { payload: TrendPoint }[];
  /** Not label: Recharts overwrites a prop of that name with the x value. */
  seriesLabel: string;
  format: TrendFormat;
};

function TrendTooltip({
  active,
  payload,
  seriesLabel,
  format,
}: TrendTooltipProps) {
  const point: TrendPoint | undefined = payload?.[0]?.payload;
  if (!active || point === undefined) {
    return null;
  }
  return (
    <div className="rounded-md border border-zinc-200 bg-background px-3 py-2 text-sm shadow-sm dark:border-zinc-800">
      <p className="text-zinc-500">{tooltipDateFormat.format(point.t)} UTC</p>
      <p className="font-medium text-foreground">
        {seriesLabel}: {formatTrendValue(point.value, format)}
      </p>
    </div>
  );
}

/**
 * One measure over time. Snapshots are only stored when something changed, so
 * the line is stepped: a value holds until the next recorded change.
 */
export function TrendChart({ label, points, format }: TrendChartProps) {
  const ticks: number[] | undefined = dayTicks(points);
  const timeTickFormat: Intl.DateTimeFormat =
    ticks === undefined ? tooltipDateFormat : tickDateFormat;

  return (
    <div className="h-48 w-full" role="img" aria-label={`${label} over time`}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart
          data={points}
          margin={{ top: 8, right: 12, bottom: 0, left: 0 }}
        >
          <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
          <XAxis
            dataKey="t"
            type="number"
            scale="time"
            domain={["dataMin", "dataMax"]}
            ticks={ticks}
            tickFormatter={(value: number) => timeTickFormat.format(value)}
            tick={{ fill: "var(--chart-muted)", fontSize: 12 }}
            tickLine={false}
            axisLine={{ stroke: "var(--chart-axis)" }}
            minTickGap={32}
          />
          <YAxis
            domain={["auto", "auto"]}
            width={52}
            tickFormatter={(value: number) => formatAxisValue(value, format)}
            tick={{ fill: "var(--chart-muted)", fontSize: 12 }}
            tickLine={false}
            axisLine={false}
            allowDecimals={format === "level"}
          />
          <Tooltip
            cursor={{ stroke: "var(--chart-axis)", strokeWidth: 1 }}
            content={<TrendTooltip seriesLabel={label} format={format} />}
            isAnimationActive={false}
          />
          <Line
            dataKey="value"
            type="stepAfter"
            stroke="var(--chart-series)"
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
            dot={false}
            activeDot={{ r: 4, stroke: "var(--background)", strokeWidth: 2 }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
