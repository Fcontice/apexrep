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
