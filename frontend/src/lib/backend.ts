import "server-only";

import { cache } from "react";
import { headers } from "next/headers";
import { z } from "zod";

import type { components } from "./api-types";
import type { PlatformSlug } from "./platform";

export const BACKEND_URL: string =
  process.env.BACKEND_URL ?? "http://localhost:8000";
const INTERNAL_TOKEN: string = process.env.INTERNAL_TOKEN ?? "";

export type ResolveResponse = components["schemas"]["ResolveResponse"];
export type PlayerProfile = components["schemas"]["PlayerProfile"];

const platformSlugSchema = z.enum(["pc", "ps", "xbox"]);

const resolveResponseSchema = z.object({
  uid: z.string(),
  platform: platformSlugSchema,
  name: z.string(),
}) satisfies z.ZodType<ResolveResponse>;

const playerProfileSchema = z.object({
  uid: z.string(),
  platform: platformSlugSchema,
  name: z.string(),
  level: z.number(),
  level_prestige: z.number(),
  level_progress: z.number(),
  rank_name: z.string().nullable(),
  rank_div: z.number().nullable(),
  rank_score: z.number().nullable(),
  selected_legend: z.string().nullable(),
  trackers: z.record(z.string(), z.number()),
  is_tracked: z.boolean(),
  tracked_since: z.string().nullable(),
  last_updated: z.string(),
  stale: z.boolean(),
}) satisfies z.ZodType<PlayerProfile>;

export type HistoryResponse = components["schemas"]["HistoryResponse"];
export type HistoryPoint = components["schemas"]["HistoryPoint"];
export type MatchesResponse = components["schemas"]["MatchesResponse"];
export type MatchItem = components["schemas"]["MatchItem"];
export type MapRotation = components["schemas"]["MapRotation"];
export type ModeRotation = components["schemas"]["ModeRotation"];
export type PredatorResponse = components["schemas"]["PredatorResponse"];
export type PredatorThreshold = components["schemas"]["PredatorThreshold"];

const historyResponseSchema = z.object({
  points: z.array(
    z.object({
      taken_at: z.string(),
      level: z.number(),
      level_prestige: z.number(),
      level_progress: z.number(),
      rank_score: z.number().nullable(),
      selected_legend: z.string().nullable(),
      trackers: z.record(z.string(), z.number()),
    }),
  ),
  bucketed: z.boolean(),
}) satisfies z.ZodType<HistoryResponse>;

const matchesResponseSchema = z.object({
  items: z.array(
    z.object({
      id: z.number(),
      kind: z.enum(["match", "session_gap"]),
      detected_at: z.string(),
      legend: z.string().nullable(),
      level_progress_delta: z.number().nullable(),
      rank_score_delta: z.number().nullable(),
      tracker_deltas: z.record(z.string(), z.number()),
    }),
  ),
  next_cursor: z.string().nullable(),
}) satisfies z.ZodType<MatchesResponse>;

const mapSlotSchema = z.object({
  map: z.string(),
  start: z.string(),
  end: z.string(),
});

const modeRotationSchema = z.object({
  current: mapSlotSchema,
  next: mapSlotSchema.nullable().optional(),
});

const mapRotationSchema = z.object({
  battle_royale: modeRotationSchema.nullable().optional(),
  ranked: modeRotationSchema.nullable().optional(),
}) satisfies z.ZodType<MapRotation>;

const predatorThresholdSchema = z.object({
  rank_score: z.number(),
  masters_and_preds: z.number(),
  updated_at: z.string(),
});

const predatorResponseSchema = z.object({
  pc: predatorThresholdSchema.nullable(),
  ps: predatorThresholdSchema.nullable(),
  xbox: predatorThresholdSchema.nullable(),
}) satisfies z.ZodType<PredatorResponse>;

export type BackendResult<T> =
  | { status: "ok"; data: T }
  | { status: "not_found" }
  | { status: "unavailable" };

/**
 * Headers every backend call carries: the shared token, and the visitor's IP
 * and user agent so the backend can rate-limit and recognise crawlers.
 */
export function backendHeaders(incoming: Headers): Headers {
  const forwardedFor: string = incoming.get("x-forwarded-for") ?? "";
  const clientIp: string = forwardedFor.split(",")[0]?.trim() ?? "";

  const outgoing = new Headers({ "X-Internal-Token": INTERNAL_TOKEN });
  if (clientIp !== "") {
    outgoing.set("X-Client-IP", clientIp);
  }
  const userAgent: string | null = incoming.get("user-agent");
  if (userAgent !== null) {
    outgoing.set("X-Client-User-Agent", userAgent);
  }
  const contentType: string | null = incoming.get("content-type");
  if (contentType !== null) {
    outgoing.set("Content-Type", contentType);
  }
  return outgoing;
}

/** A lookup the backend limits per visitor can also come back rate limited. */
export type LimitedResult<T> = BackendResult<T> | { status: "rate_limited" };

async function getJsonLimited<T>(
  path: string,
  schema: z.ZodType<T>,
): Promise<LimitedResult<T>> {
  let response: Response;
  try {
    response = await fetch(`${BACKEND_URL}${path}`, {
      headers: backendHeaders(await headers()),
      cache: "no-store",
    });
  } catch {
    return { status: "unavailable" };
  }
  if (response.status === 404 || response.status === 422) {
    return { status: "not_found" };
  }
  if (response.status === 429) {
    return { status: "rate_limited" };
  }
  if (!response.ok) {
    return { status: "unavailable" };
  }
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    return { status: "unavailable" };
  }
  const parsed = schema.safeParse(body);
  return parsed.success
    ? { status: "ok", data: parsed.data }
    : { status: "unavailable" };
}

async function getJson<T>(
  path: string,
  schema: z.ZodType<T>,
): Promise<BackendResult<T>> {
  const result = await getJsonLimited(path, schema);
  return result.status === "rate_limited" ? { status: "unavailable" } : result;
}

export async function resolvePlayer(
  platform: PlatformSlug,
  name: string,
): Promise<LimitedResult<ResolveResponse>> {
  const query = new URLSearchParams({ platform, name });
  return getJsonLimited(
    `/api/resolve?${query.toString()}`,
    resolveResponseSchema,
  );
}

export async function getPlayerHistory(
  platform: PlatformSlug,
  uid: string,
  days: number,
): Promise<BackendResult<HistoryResponse>> {
  return getJson(
    `/api/players/${platform}/${uid}/history?days=${days}`,
    historyResponseSchema,
  );
}

export async function getPlayerMatches(
  platform: PlatformSlug,
  uid: string,
  before: string | null,
): Promise<BackendResult<MatchesResponse>> {
  const query = new URLSearchParams();
  if (before !== null) {
    query.set("before", before);
  }
  const suffix: string = query.size > 0 ? `?${query.toString()}` : "";
  return getJson(
    `/api/players/${platform}/${uid}/matches${suffix}`,
    matchesResponseSchema,
  );
}

export type SitemapResponse = components["schemas"]["SitemapResponse"];

const sitemapResponseSchema = z.object({
  players: z.array(
    z.object({
      platform: platformSlugSchema,
      uid: z.string(),
      last_updated: z.string().nullable(),
    }),
  ),
}) satisfies z.ZodType<SitemapResponse>;

export async function getSitemapPlayers(): Promise<
  BackendResult<SitemapResponse>
> {
  return getJson("/api/sitemap/players", sitemapResponseSchema);
}

export async function getMapRotation(): Promise<BackendResult<MapRotation>> {
  return getJson("/api/meta/maps", mapRotationSchema);
}

export async function getPredatorThresholds(): Promise<
  BackendResult<PredatorResponse>
> {
  return getJson("/api/meta/predator", predatorResponseSchema);
}

export type TrackOutcome =
  "ok" | "full" | "not_found" | "rate_limited" | "unavailable";

export async function trackPlayer(
  platform: PlatformSlug,
  uid: string,
): Promise<TrackOutcome> {
  let response: Response;
  try {
    response = await fetch(
      `${BACKEND_URL}/api/players/${platform}/${uid}/track`,
      {
        method: "POST",
        headers: backendHeaders(await headers()),
        cache: "no-store",
      },
    );
  } catch {
    return "unavailable";
  }
  if (response.ok) {
    return "ok";
  }
  if (response.status === 409) {
    return "full";
  }
  if (response.status === 429) {
    return "rate_limited";
  }
  return response.status === 404 ? "not_found" : "unavailable";
}

/** Cached per request, so generateMetadata and the page share one backend call. */
export const getPlayerProfile = cache(
  async (
    platform: PlatformSlug,
    uid: string,
  ): Promise<BackendResult<PlayerProfile>> =>
    getJson(`/api/players/${platform}/${uid}`, playerProfileSchema),
);
