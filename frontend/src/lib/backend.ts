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

async function getJson<T>(
  path: string,
  schema: z.ZodType<T>,
): Promise<BackendResult<T>> {
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
  if (!response.ok) {
    return { status: "unavailable" };
  }
  const parsed = schema.safeParse(await response.json());
  return parsed.success
    ? { status: "ok", data: parsed.data }
    : { status: "unavailable" };
}

export async function resolvePlayer(
  platform: PlatformSlug,
  name: string,
): Promise<BackendResult<ResolveResponse>> {
  const query = new URLSearchParams({ platform, name });
  return getJson(`/api/resolve?${query.toString()}`, resolveResponseSchema);
}

export type TrackOutcome = "ok" | "full" | "not_found" | "unavailable";

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
