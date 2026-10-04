import { SearchForm } from "@/components/search-form";

export function PlayerNotFound() {
  return (
    <main className="mx-auto flex w-full max-w-xl flex-1 flex-col justify-center gap-6 px-4 py-16">
      <h1 className="text-2xl font-semibold tracking-tight">
        Player not found
      </h1>
      <div className="flex flex-col gap-3 text-zinc-600 dark:text-zinc-400">
        <p>
          On PC, players are found by their <strong>EA ID</strong>, not their
          Steam name. The two are usually different, and renaming your Steam
          profile does not change your EA ID.
        </p>
        <p>
          To find yours: go to ea.com, choose Sign In, pick the Steam option,
          then open Account Settings. The EA ID is listed under About Me.
        </p>
      </div>
      <SearchForm />
    </main>
  );
}
