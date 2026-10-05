import Link from "next/link";
import type { ReactNode } from "react";

import type { PlayerProfile } from "@/lib/backend";
import { PLATFORM_LABELS } from "@/lib/platform";

export type ProfileTab = "overview" | "trends" | "matches";

const TABS: { tab: ProfileTab; label: string; suffix: string }[] = [
  { tab: "overview", label: "Overview", suffix: "" },
  { tab: "trends", label: "Trends", suffix: "/trends" },
  { tab: "matches", label: "Matches", suffix: "/matches" },
];

type ProfileShellProps = {
  profile: PlayerProfile;
  active: ProfileTab;
  children: ReactNode;
};

/** The header and tab bar shared by the three profile pages. */
export function ProfileShell({ profile, active, children }: ProfileShellProps) {
  const base = `/player/${profile.platform}/${profile.uid}`;

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-8 px-4 py-10">
      <header className="flex flex-col gap-1">
        <p className="text-sm text-zinc-500">
          {PLATFORM_LABELS[profile.platform]}
        </p>
        <h1 className="break-words text-3xl font-semibold tracking-tight">
          {profile.name}
        </h1>
      </header>

      <nav
        aria-label="Player sections"
        className="flex gap-1 border-b border-zinc-200 dark:border-zinc-800"
      >
        {TABS.map(({ tab, label, suffix }) => (
          <Link
            key={tab}
            href={`${base}${suffix}`}
            aria-current={tab === active ? "page" : undefined}
            className={
              tab === active
                ? "-mb-px border-b-2 border-foreground px-3 py-2 font-medium"
                : "-mb-px border-b-2 border-transparent px-3 py-2 text-zinc-500 hover:text-foreground"
            }
          >
            {label}
          </Link>
        ))}
      </nav>

      {children}
    </main>
  );
}

export function ProfileUnavailable() {
  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col justify-center gap-4 px-4 py-16">
      <h1 className="text-2xl font-semibold tracking-tight">
        Stats are unavailable right now
      </h1>
      <p className="text-zinc-600 dark:text-zinc-400">
        The stats service did not answer and there is no saved copy of this
        player yet. Try again in a minute.
      </p>
    </main>
  );
}
