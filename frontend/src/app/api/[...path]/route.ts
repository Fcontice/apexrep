import type { NextRequest } from "next/server";

import { BACKEND_URL, backendHeaders } from "@/lib/backend";

/**
 * Forwards browser calls to the FastAPI backend. The browser never talks to
 * the backend directly, so the internal token stays on the server.
 */
async function forward(
  request: NextRequest,
  context: RouteContext<"/api/[...path]">,
): Promise<Response> {
  const { path } = await context.params;
  const target = new URL(
    `/api/${path.map(encodeURIComponent).join("/")}`,
    BACKEND_URL,
  );
  target.search = request.nextUrl.search;

  const hasBody: boolean =
    request.method !== "GET" && request.method !== "HEAD";
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers: backendHeaders(request.headers),
      body: hasBody ? await request.text() : undefined,
      cache: "no-store",
    });
  } catch {
    return Response.json({ detail: "upstream_unavailable" }, { status: 503 });
  }

  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type":
        upstream.headers.get("content-type") ?? "application/json",
    },
  });
}

export { forward as GET, forward as POST, forward as DELETE };
