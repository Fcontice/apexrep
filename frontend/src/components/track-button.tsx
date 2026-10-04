"use client";

import { useActionState } from "react";

import { trackPlayerAction, type TrackState } from "@/app/actions";
import type { TrackOutcome } from "@/lib/backend";
import type { PlatformSlug } from "@/lib/platform";

const FAILURE_MESSAGES: Record<Exclude<TrackOutcome, "ok">, string> = {
  full: "Tracking is full right now. Try again later.",
  not_found: "This player could not be found.",
  unavailable: "Tracking could not be started. Try again in a minute.",
};

const INITIAL_STATE: TrackState = { outcome: null };

type TrackButtonProps = {
  platform: PlatformSlug;
  uid: string;
};

export function TrackButton({ platform, uid }: TrackButtonProps) {
  const [state, formAction, pending] = useActionState(
    trackPlayerAction.bind(null, platform, uid),
    INITIAL_STATE,
  );
  const failure: string | null =
    state.outcome !== null && state.outcome !== "ok"
      ? FAILURE_MESSAGES[state.outcome]
      : null;

  return (
    <form action={formAction} className="flex flex-col gap-2">
      <button
        type="submit"
        disabled={pending}
        className="h-11 self-start rounded-lg bg-foreground px-5 font-medium text-background disabled:opacity-60"
      >
        {pending ? "Starting…" : "Track this player"}
      </button>
      {failure !== null ? (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {failure}
        </p>
      ) : null}
    </form>
  );
}
