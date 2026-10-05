"use client";

type ErrorPageProps = {
  error: Error & { digest?: string };
  /** Re-fetches and re-renders the failed segment. */
  retry: () => void;
};

export default function ErrorPage({ retry }: ErrorPageProps) {
  return (
    <main className="mx-auto flex w-full max-w-xl flex-1 flex-col justify-center gap-4 px-4 py-16">
      <h1 className="text-2xl font-semibold tracking-tight">
        Something went wrong
      </h1>
      <p className="text-zinc-600 dark:text-zinc-400">
        This page could not be shown. Trying again usually fixes it.
      </p>
      <button
        type="button"
        onClick={() => retry()}
        className="h-11 self-start rounded-lg bg-foreground px-5 font-medium text-background"
      >
        Try again
      </button>
    </main>
  );
}
