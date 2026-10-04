import { connection } from "next/server";

import { fetchBackendHealth, type BackendHealth } from "@/lib/backend";

function statusLabel(health: BackendHealth | null): string {
  if (health === null) {
    return "unreachable";
  }
  return health.status;
}

export default async function Home() {
  await connection();
  const health: BackendHealth | null = await fetchBackendHealth();

  return (
    <main className="mx-auto flex w-full max-w-xl flex-1 flex-col justify-center gap-6 px-4 py-16">
      <h1 className="text-3xl font-semibold tracking-tight">ApexRep</h1>
      <p className="text-zinc-600 dark:text-zinc-400">
        Apex Legends stats tracker. Scaffold only: player lookup arrives in
        Phase 3.
      </p>
      <dl className="grid grid-cols-2 gap-2 rounded-lg border border-zinc-200 p-4 font-mono text-sm dark:border-zinc-800">
        <dt>backend</dt>
        <dd data-testid="backend-status">{statusLabel(health)}</dd>
        <dt>database</dt>
        <dd>{health?.database ? "up" : "down"}</dd>
        <dt>worker</dt>
        <dd>{health?.worker_alive ? "alive" : "no heartbeat"}</dd>
        <dt>last heartbeat</dt>
        <dd>{health?.worker_heartbeat_at ?? "none"}</dd>
      </dl>
    </main>
  );
}
