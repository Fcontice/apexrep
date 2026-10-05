import "server-only";

import {
  getPlayerProfile,
  type BackendResult,
  type PlayerProfile,
} from "./backend";
import { isPlatformSlug } from "./platform";

const UID_PATTERN = /^[0-9]{1,20}$/;

/** Validates the route params shared by every profile tab, then loads the profile. */
export async function loadProfile(params: {
  platform: string;
  uid: string;
}): Promise<BackendResult<PlayerProfile>> {
  if (!isPlatformSlug(params.platform) || !UID_PATTERN.test(params.uid)) {
    return { status: "not_found" };
  }
  return getPlayerProfile(params.platform, params.uid);
}
