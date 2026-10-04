import { SearchForm } from "@/components/search-form";

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-xl flex-1 flex-col justify-center gap-6 px-4 py-16">
      <h1 className="text-3xl font-semibold tracking-tight">ApexRep</h1>
      <p className="text-zinc-600 dark:text-zinc-400">
        Look up an Apex Legends player to see their level, rank and the trackers
        on their selected legend.
      </p>
      <SearchForm />
      <p className="text-sm text-zinc-500">
        Playing on Steam? Search with your EA ID, which is usually not your
        Steam name.
      </p>
    </main>
  );
}
