import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";

import { SearchForm } from "@/components/search-form";
import { resolvePlayer } from "@/lib/backend";
import { isPlatformSlug } from "@/lib/platform";

// Name URLs are an entry point only; the canonical profile URL is what gets indexed.
export const metadata: Metadata = {
  title: "Finding player · ApexRep",
  robots: { index: false, follow: false },
};

function decodeName(raw: string): string | null {
  try {
    return decodeURIComponent(raw).trim();
  } catch {
    return null;
  }
}

export default async function ResolvePage(
  props: PageProps<"/[platform]/[name]">,
) {
  const { platform, name: rawName } = await props.params;
  const name: string | null = decodeName(rawName);
  if (!isPlatformSlug(platform) || name === null || name === "") {
    notFound();
  }

  const result = await resolvePlayer(platform, name);
  if (result.status === "ok") {
    // Temporary: a name can later belong to a different player.
    redirect(`/player/${result.data.platform}/${result.data.uid}`);
  }
  if (result.status === "not_found") {
    notFound();
  }

  return (
    <main className="mx-auto flex w-full max-w-xl flex-1 flex-col justify-center gap-6 px-4 py-16">
      <h1 className="text-2xl font-semibold tracking-tight">
        {result.status === "rate_limited"
          ? "Too many lookups"
          : "Stats are unavailable right now"}
      </h1>
      <p className="text-zinc-600 dark:text-zinc-400">
        {result.status === "rate_limited"
          ? "You have looked up a lot of players in a short time. Try again in a few minutes."
          : "The stats service did not answer. Try again in a minute."}
      </p>
      <SearchForm defaultPlatform={platform} defaultName={name} />
    </main>
  );
}
