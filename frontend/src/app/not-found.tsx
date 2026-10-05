import Link from "next/link";

export default function NotFound() {
  return (
    <main className="mx-auto flex w-full max-w-xl flex-1 flex-col justify-center gap-4 px-4 py-16">
      <h1 className="text-2xl font-semibold tracking-tight">Page not found</h1>
      <p className="text-zinc-600 dark:text-zinc-400">
        There is nothing at this address.
      </p>
      <Link href="/" className="underline">
        Search for a player
      </Link>
    </main>
  );
}
