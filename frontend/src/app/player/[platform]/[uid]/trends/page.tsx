import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { ProfileShell, ProfileUnavailable } from "@/components/profile-shell";
import { TrendChart } from "@/components/trend-chart";
import {
  getPlayerHistory,
  type HistoryPoint,
  type PlayerProfile,
} from "@/lib/backend";
import { formatTrackerKey, formatUpdatedAt } from "@/lib/format";
import { loadProfile } from "@/lib/profile-page";
import {
  formatTrendValue,
  type TrendFormat,
  type TrendPoint,
} from "@/lib/trend";

const HISTORY_DAYS = 30;
const LEVELS_PER_TIER = 500;
const TABLE_ROWS = 50;

type TrendsPageProps = PageProps<"/player/[platform]/[uid]/trends">;

type Series = {
  key: string;
  title: string;
  format: TrendFormat;
  points: TrendPoint[];
};

export async function generateMetadata(
  props: TrendsPageProps,
): Promise<Metadata> {
  const result = await loadProfile(await props.params);
  return {
    title:
      result.status === "ok"
        ? `${result.data.name} · Trends · ApexRep`
        : "Trends · ApexRep",
  };
}

function buildSeries(history: HistoryPoint[]): Series[] {
  const time = (point: HistoryPoint): number => Date.parse(point.taken_at);

  const series: Series[] = [
    {
      key: "level",
      title: "Account level (across all tiers)",
      format: "level",
      points: history.map((point) => ({
        t: time(point),
        value:
          point.level_prestige * LEVELS_PER_TIER +
          point.level +
          point.level_progress / 100,
      })),
    },
    {
      key: "rank_score",
      title: "Rank score (RP)",
      format: "integer",
      points: history.flatMap((point) =>
        point.rank_score === null
          ? []
          : [{ t: time(point), value: point.rank_score }],
      ),
    },
  ];

  // Trackers belong to the selected legend, so "kills" on Wraith and "kills" on
  // Octane are different counters and get separate charts.
  const trackerSeries = new Map<string, Series>();
  for (const point of history) {
    const legend: string = point.selected_legend ?? "Unknown legend";
    for (const [trackerKey, value] of Object.entries(point.trackers)) {
      const seriesKey = `tracker:${legend}:${trackerKey}`;
      let entry: Series | undefined = trackerSeries.get(seriesKey);
      if (entry === undefined) {
        entry = {
          key: seriesKey,
          title: `${formatTrackerKey(trackerKey)} · ${legend}`,
          format: "integer",
          points: [],
        };
        trackerSeries.set(seriesKey, entry);
      }
      entry.points.push({ t: time(point), value });
    }
  }
  series.push(
    ...[...trackerSeries.values()].sort((a, b) =>
      a.title.localeCompare(b.title),
    ),
  ); // A line needs two points.
  return series.filter((entry) => entry.points.length >= 2);
}

function TrendCard({ series }: { series: Series }) {
  const latest: TrendPoint = series.points[series.points.length - 1];
  const tableRows: TrendPoint[] = series.points.slice(-TABLE_ROWS).reverse();

  return (
    <section className="flex flex-col gap-3 rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="font-semibold">{series.title}</h2>
        <p className="text-sm text-zinc-500">
          Latest{" "}
          <span className="font-medium text-foreground">
            {formatTrendValue(latest.value, series.format)}
          </span>
        </p>
      </div>
      <TrendChart
        label={series.title}
        points={series.points}
        format={series.format}
      />
      <details className="text-sm">
        <summary className="cursor-pointer text-zinc-500">
          View as table
        </summary>
        <table className="mt-2 w-full text-left tabular-nums">
          <thead className="text-zinc-500">
            <tr>
              <th className="py-1 font-normal">Time</th>
              <th className="py-1 text-right font-normal">{series.title}</th>
            </tr>
          </thead>
          <tbody>
            {tableRows.map((point) => (
              <tr
                key={point.t}
                className="border-t border-zinc-200 dark:border-zinc-800"
              >
                <td className="py-1">
                  {formatUpdatedAt(new Date(point.t).toISOString())}
                </td>
                <td className="py-1 text-right">
                  {formatTrendValue(point.value, series.format)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </section>
  );
}

export default async function TrendsPage(props: TrendsPageProps) {
  const result = await loadProfile(await props.params);
  if (result.status === "not_found") {
    notFound();
  }
  if (result.status === "unavailable") {
    return <ProfileUnavailable />;
  }
  const profile: PlayerProfile = result.data;
  const history = await getPlayerHistory(
    profile.platform,
    profile.uid,
    HISTORY_DAYS,
  );
  const series: Series[] =
    history.status === "ok" ? buildSeries(history.data.points) : [];

  return (
    <ProfileShell profile={profile} active="trends">
      {history.status !== "ok" ? (
        <p className="text-zinc-600 dark:text-zinc-400">
          History could not be loaded. Try again in a minute.
        </p>
      ) : series.length === 0 ? (
        <p className="text-zinc-600 dark:text-zinc-400">
          Not enough history yet. Charts appear once this player&apos;s stats
          have changed at least once while ApexRep was checking them
          {profile.is_tracked ? "." : "; turn on tracking on the Overview tab."}
        </p>
      ) : (
        <>
          <p className="text-sm text-zinc-500">
            Last {HISTORY_DAYS} days. Each chart has its own scale, and tracker
            charts are per legend. Values are recorded when they change, so a
            flat stretch means nothing changed.
            {history.data.bucketed ? " Shown as one value per hour." : ""}
          </p>
          {series.map((entry) => (
            <TrendCard key={entry.key} series={entry} />
          ))}
        </>
      )}
    </ProfileShell>
  );
}
