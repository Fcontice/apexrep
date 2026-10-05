import type { MetadataRoute } from "next";

import { getSitemapPlayers } from "@/lib/backend";
import { SITE_URL } from "@/lib/site";

/**
 * The home page plus tracked players' canonical profile URLs. Name URLs
 * (/pc/<name>) are entry points only and are deliberately left out.
 */
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const entries: MetadataRoute.Sitemap = [
    { url: SITE_URL, changeFrequency: "daily" },
  ];

  const result = await getSitemapPlayers();
  if (result.status !== "ok") {
    return entries;
  }
  for (const player of result.data.players) {
    entries.push({
      url: `${SITE_URL}/player/${player.platform}/${player.uid}`,
      lastModified: player.last_updated ?? undefined,
      changeFrequency: "hourly",
    });
  }
  return entries;
}
