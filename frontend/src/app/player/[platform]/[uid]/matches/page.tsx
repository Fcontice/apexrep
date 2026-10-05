import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ProfileShell, ProfileUnavailable } from "@/components/profile-shell";
import {
  getPlayerMatches,
  type MatchItem,
  type PlayerProfile,
} from "@/lib/backend";
import {
  formatNumber,
  formatSigned,
  formatTrackerKey,
  formatUpdatedAt,
} from "@/lib/format";
import { loadProfile } from "@/lib/profile-page";

type MatchesPageProps = PageProps<"/player/[platform]/[uid]/matches">;

export async function generateMetadata(
  props: MatchesPageProps,
): Promise<Metadata> {
  const result = await loadProfile(await props.params);
  return {
    title:
      result.status === "ok"
        ? `${result.data.name} · Matches · ApexRep`
        : "Matches · ApexRep",
  };
}

function trackerSummary(deltas: Record<string, number>): string {
  const entries: [string, number][] = Object.entries(deltas);
  if (entries.length === 0) {
    return "–";
  }
  return entries
    .map(([key, value]) => `${formatTrackerKey(key)} +${formatNumber(value)}`)
    .join(" · ");
}

function MatchRow({ match }: { match: MatchItem }) {
  const time: string = formatUpdatedAt(match.detected_at);
  if (match.kind === "session_gap") {
    return (
      <tr className="border-t border-zinc-200 text-zinc-500 dark:border-zinc-800">
        <td className="py-2 pr-4 whitespace-nowrap">{time}</td>
        <td className="py-2" colSpan={4}>
          Untracked activity: this player progressed while ApexRep was not
          checking them.
        </td>
      </tr>
    );
  }
  return (
    <tr className="border-t border-zinc-200 dark:border-zinc-800">
      <td className="py-2 pr-4 whitespace-nowrap">{time}</td>
      <td className="py-2 pr-4">{match.legend ?? "–"}</td>
      <td className="py-2 pr-4 text-right whitespace-nowrap">
        {match.level_progress_delta === null
          ? "–"
          : `${formatSigned(match.level_progress_delta)}%`}
      </td>
      <td className="py-2 pr-4 text-right whitespace-nowrap">
        {match.rank_score_delta === null
          ? "–"
          : formatSigned(match.rank_score_delta)}
      </td>
      <td className="py-2 whitespace-nowrap">
        {trackerSummary(match.tracker_deltas)}
      </td>
    </tr>
  );
}

export default async function MatchesPage(props: MatchesPageProps) {
  const result = await loadProfile(await props.params);
  if (result.status === "not_found") {
    notFound();
  }
  if (result.status === "unavailable") {
    return <ProfileUnavailable />;
  }
  const profile: PlayerProfile = result.data;

  const { before } = await props.searchParams;
  const cursor: string | null = typeof before === "string" ? before : null;
  const matches = await getPlayerMatches(profile.platform, profile.uid, cursor);
  const base = `/player/${profile.platform}/${profile.uid}/matches`;

  return (
    <ProfileShell profile={profile} active="matches">
      {matches.status !== "ok" ? (
        <p className="text-zinc-600 dark:text-zinc-400">
          Matches could not be loaded. Try again in a minute.
        </p>
      ) : matches.data.items.length === 0 ? (
        <p className="text-zinc-600 dark:text-zinc-400">
          No matches recorded yet.{" "}
          {profile.is_tracked
            ? "They appear here a few minutes after this player finishes a game."
            : "Turn on tracking on the Overview tab to start building a match history."}
        </p>
      ) : (
        <>
          <p className="text-sm text-zinc-500">
            Built from changes between checks, so each row is one or more
            matches (1+), and only equipped trackers are counted. Times are when
            the change was seen, in UTC.
          </p>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[38rem] text-left text-sm tabular-nums">
              <thead className="text-zinc-500">
                <tr>
                  <th className="py-2 pr-4 font-normal">Seen</th>
                  <th className="py-2 pr-4 font-normal">Legend</th>
                  <th className="py-2 pr-4 text-right font-normal">Level</th>
                  <th className="py-2 pr-4 text-right font-normal">RP</th>
                  <th className="py-2 font-normal">Trackers</th>
                </tr>
              </thead>
              <tbody>
                {matches.data.items.map((match) => (
                  <MatchRow key={match.id} match={match} />
                ))}
              </tbody>
            </table>
          </div>
          <nav className="flex gap-4 text-sm" aria-label="Match pages">
            {cursor !== null ? (
              <Link href={base} className="underline">
                Newest
              </Link>
            ) : null}
            {matches.data.next_cursor !== null ? (
              <Link
                href={`${base}?before=${encodeURIComponent(matches.data.next_cursor)}`}
                className="underline"
              >
                Older matches
              </Link>
            ) : null}
          </nav>
        </>
      )}
    </ProfileShell>
  );
}
