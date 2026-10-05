const numberFormat = new Intl.NumberFormat("en-US");

const updatedFormat = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
  timeZone: "UTC",
});

export function formatNumber(value: number): string {
  return numberFormat.format(value);
}

/** 25 -> "+25", -20 -> "−20", 0 -> "0" */
export function formatSigned(value: number): string {
  if (value === 0) {
    return "0";
  }
  const magnitude: string = numberFormat.format(Math.abs(value));
  return value > 0 ? `+${magnitude}` : `−${magnitude}`;
}

const timeFormat = new Intl.DateTimeFormat("en-US", {
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
  timeZone: "UTC",
});

/** "00:30 UTC" */
export function formatTimeUtc(iso: string): string {
  return `${timeFormat.format(new Date(iso))} UTC`;
}

/** "career_kills" -> "Career kills" */
export function formatTrackerKey(key: string): string {
  const words: string = key.replaceAll("_", " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function formatRank(
  rankName: string | null,
  rankDiv: number | null,
): string {
  if (rankName === null) {
    return "Unranked";
  }
  // Master and Predator have no divisions; ALS reports those as 0.
  return rankDiv !== null && rankDiv > 0 ? `${rankName} ${rankDiv}` : rankName;
}

export function formatUpdatedAt(iso: string): string {
  return `${updatedFormat.format(new Date(iso))} UTC`;
}

/** ALS counts prestiges from 0; the game shows tiers 1 to 4. */
export function levelTier(levelPrestige: number): number {
  return levelPrestige + 1;
}
