import type { components } from "./api-types";

export type PlatformSlug = components["schemas"]["PlatformSlug"];

export const PLATFORM_LABELS: Record<PlatformSlug, string> = {
  pc: "PC",
  ps: "PlayStation",
  xbox: "Xbox",
};

export const PLATFORM_SLUGS: PlatformSlug[] = ["pc", "ps", "xbox"];

export function isPlatformSlug(value: string): value is PlatformSlug {
  return (PLATFORM_SLUGS as string[]).includes(value);
}
