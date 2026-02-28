/** Proxy /api/threads/stream-ui?key=... → FastAPI /api/threads/stream-ui?key=... as SSE */

const API_URL = process.env.AI_V2_API_URL || "http://api:8000";
const API_KEY = process.env.AI_V2_API_KEY || "";

export const dynamic = "force-dynamic";
export const fetchCache = "force-no-store";
export const maxDuration = 300;

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const key = searchParams.get("key") || "";
  const liveOnly = searchParams.get("live_only") || "";
  if (!key) {
    return Response.json({ error: "Missing thread key" }, { status: 400 });
  }

  const upstreamParams = new URLSearchParams({ key });
  if (liveOnly) {
    upstreamParams.set("live_only", liveOnly);
  }

  const upstream = await fetch(
    `${API_URL}/api/threads/stream-ui?${upstreamParams.toString()}`,
    {
      headers: { Authorization: `Bearer ${API_KEY}` },
      cache: "no-store",
      signal: request.signal,
    },
  );

  if (!upstream.ok || !upstream.body) {
    return Response.json(
      { error: `Stream not available: ${key}` },
      { status: upstream.status },
    );
  }

  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
      "x-vercel-ai-ui-message-stream": "v1",
    },
  });
}
