import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { ProfileShell, ProfileUnavailable } from "@/components/profile-shell";
import { TrackButton } from "@/components/track-button";
import type { PlayerProfile } from "@/lib/backend";
import {
  formatNumber,
  formatRank,
  formatTrackerKey,
  formatUpdatedAt,
  levelTier,
} from "@/lib/format";
import { PLATFORM_LABELS } from "@/lib/platform";
import { loadProfile } from "@/lib/profile-page";

type ProfilePageProps = PageProps<"/player/[platform]/[uid]">;

export async function generateMetadata(
  props: ProfilePageProps,
): Promise<Metadata> {
  const result = await loadProfile(await props.params);
  if (result.status !== "ok") {
    return { title: "Player · ApexRep" };
  }
  const profile: PlayerProfile = result.data;
  const platformLabel: string = PLATFORM_LABELS[profile.platform];
  const title = `${profile.name} · ${platformLabel} · Apex Legends stats`;
  const description = `${profile.name} on ${platformLabel}: level ${profile.level}, ${formatRank(profile.rank_name, profile.rank_div)}.`;
  return {
    title,
    description,
    alternates: { canonical: `/player/${profile.platform}/${profile.uid}` },
    openGraph: { title, description, type: "profile" },
  };
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
      <dt className="text-sm text-zinc-500">{label}</dt>
      <dd className="mt-1 text-xl font-semibold">{value}</dd>
    </div>
  );
}

export default async function ProfilePage(props: ProfilePageProps) {
  const result = await loadProfile(await props.params);
  if (result.status === "not_found") {
    notFound();
  }
  if (result.status === "unavailable") {
    return <ProfileUnavailable />;
  }

  const profile: PlayerProfile = result.data;
  const trackers: [string, number][] = Object.entries(profile.trackers);

  return (
    <ProfileShell profile={profile} active="overview">
      <dl className="grid grid-cols-2 gap-3">
        <Stat
          label={`Level · tier ${levelTier(profile.level_prestige)} of 4`}
          value={`${profile.level} (${profile.level_progress}%)`}
        />
        <Stat
          label="Rank (BR)"
          value={
            profile.rank_score === null
              ? formatRank(profile.rank_name, profile.rank_div)
              : `${formatRank(profile.rank_name, profile.rank_div)} · ${formatNumber(profile.rank_score)} RP`
          }
        />
      </dl>

      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold">
          Selected legend: {profile.selected_legend ?? "unknown"}
        </h2>
        {trackers.length === 0 ? (
          <p className="text-zinc-600 dark:text-zinc-400">
            No trackers are equipped on this legend.
          </p>
        ) : (
          <dl className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {trackers.map(([key, value]) => (
              <Stat
                key={key}
                label={formatTrackerKey(key)}
                value={formatNumber(value)}
              />
            ))}
          </dl>
        )}
        <p className="text-sm text-zinc-500">
          Stats only cover the trackers this player has equipped on their
          selected legend, so they are a partial picture.
        </p>
      </section>

      <section className="flex flex-col gap-3 rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
        <h2 className="text-lg font-semibold">Match tracking</h2>
        {profile.is_tracked && profile.tracked_since !== null ? (
          <p className="text-zinc-600 dark:text-zinc-400">
            Tracking since {formatUpdatedAt(profile.tracked_since)}. Tracking
            stops after 14 days without a visit to this page.
          </p>
        ) : (
          <>
            <p className="text-zinc-600 dark:text-zinc-400">
              Apex has no public match history. Turn on tracking and ApexRep
              checks this player every few minutes and builds one from the
              changes it sees.
            </p>
            <TrackButton platform={profile.platform} uid={profile.uid} />
          </>
        )}
      </section>

      <p className="text-sm text-zinc-500">
        Last updated {formatUpdatedAt(profile.last_updated)}
        {profile.stale
          ? ". Newer data could not be loaded, so this may be out of date."
          : "."}
      </p>
    </ProfileShell>
  );
}
