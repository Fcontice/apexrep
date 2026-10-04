import { z } from "zod";

const BACKEND_URL: string = process.env.BACKEND_URL ?? "http://localhost:8000";

const healthSchema = z.object({
  status: z.enum(["ok", "degraded", "down"]),
  database: z.boolean(),
  worker_alive: z.boolean(),
  worker_heartbeat_at: z.string().nullable(),
});

export type BackendHealth = z.infer<typeof healthSchema>;

/** Returns null when the backend is unreachable or answers with an unexpected body. */
export async function fetchBackendHealth(): Promise<BackendHealth | null> {
  try {
    const response: Response = await fetch(`${BACKEND_URL}/api/health`, {
      cache: "no-store",
    });
    const parsed = healthSchema.safeParse(await response.json());
    return parsed.success ? parsed.data : null;
  } catch {
    return null;
  }
}
