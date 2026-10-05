import {
  getMapRotation,
  getPredatorThresholds,
  type ModeRotation,
  type PredatorThreshold,
} from "@/lib/backend";
import { formatNumber, formatTimeUtc } from "@/lib/format";
import {
  PLATFORM_LABELS,
  PLATFORM_SLUGS,
  type PlatformSlug,
} from "@/lib/platform";

function Card({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-3 rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
      <h2 className="font-semibold">{title}</h2>
      {children}
    </section>
  );
}

function ModeRow({
  label,
  rotation,
}: {
  label: string;
  rotation: ModeRotation;
}) {
  return (
    <div>
      <dt className="text-sm text-zinc-500">{label}</dt>
      <dd>
        <span className="font-medium">{rotation.current.map}</span>{" "}
        <span className="text-sm text-zinc-500">
          until {formatTimeUtc(rotation.current.end)}
          {rotation.next ? `, then ${rotation.next.map}` : ""}
        </span>
      </dd>
    </div>
  );
}

/** Renders nothing if the rotation cannot be loaded; the home page works without it. */
export async function MapRotationCard() {
  const result = await getMapRotation();
  if (result.status !== "ok") {
    return null;
  }
  const { battle_royale: battleRoyale, ranked } = result.data;
  if (!battleRoyale && !ranked) {
    return null;
  }
  return (
    <Card title="Map rotation">
      <dl className="flex flex-col gap-2">
        {battleRoyale ? (
          <ModeRow label="Battle Royale" rotation={battleRoyale} />
        ) : null}
        {ranked ? <ModeRow label="Ranked" rotation={ranked} /> : null}
      </dl>
    </Card>
  );
}

export async function PredatorCard() {
  const result = await getPredatorThresholds();
  if (result.status !== "ok") {
    return null;
  }
  const rows: [PlatformSlug, PredatorThreshold][] = PLATFORM_SLUGS.flatMap(
    (slug): [PlatformSlug, PredatorThreshold][] => {
      const threshold: PredatorThreshold | null = result.data[slug];
      return threshold === null ? [] : [[slug, threshold]];
    },
  );
  if (rows.length === 0) {
    return null;
  }
  return (
    <Card title="RP needed for Predator">
      <dl className="grid grid-cols-3 gap-3">
        {rows.map(([slug, threshold]) => (
          <div key={slug}>
            <dt className="text-sm text-zinc-500">{PLATFORM_LABELS[slug]}</dt>
            <dd className="text-lg font-semibold">
              {formatNumber(threshold.rank_score)}
            </dd>
            <dd className="text-xs text-zinc-500">
              {formatNumber(threshold.masters_and_preds)} Masters and Predators
            </dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}
