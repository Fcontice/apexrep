"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { trackPlayer, type TrackOutcome } from "@/lib/backend";
import { isPlatformSlug } from "@/lib/platform";

const UID_PATTERN = /^[0-9]{1,20}$/;

export type TrackState = { outcome: TrackOutcome | null };

export async function searchPlayer(formData: FormData): Promise<void> {
  const platform: FormDataEntryValue | null = formData.get("platform");
  const name: FormDataEntryValue | null = formData.get("name");

  if (
    typeof platform !== "string" ||
    !isPlatformSlug(platform) ||
    typeof name !== "string" ||
    name.trim() === ""
  ) {
    redirect("/");
  }
  redirect(`/${platform}/${encodeURIComponent(name.trim())}`);
}

/** Bound to a player and passed to useActionState; the form itself carries no fields. */
export async function trackPlayerAction(
  platform: string,
  uid: string,
): Promise<TrackState> {
  if (!isPlatformSlug(platform) || !UID_PATTERN.test(uid)) {
    return { outcome: "not_found" };
  }
  const outcome: TrackOutcome = await trackPlayer(platform, uid);
  if (outcome === "ok") {
    revalidatePath(`/player/${platform}/${uid}`);
  }
  return { outcome };
}
