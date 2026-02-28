/** Proxy /api/threads/stream?key=... → FastAPI /api/threads/stream?key=... as SSE */

const API_URL = process.env.AI_V2_API_URL || "http://api:8000";
const API_KEY = process.env.AI_V2_API_KEY || "";

export const dynamic = "force-dynamic";
export const fetchCache = "force-no-store";
export const maxDuration = 300;

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const key = searchParams.get("key") || "";
  if (!key) {
    return Response.json({ error: "Missing thread key" }, { status: 400 });
  }

  const upstream = await fetch(
    `${API_URL}/api/threads/stream?key=${encodeURIComponent(key)}`,
    {
      headers: { Authorization: `Bearer ${API_KEY}` },
      cache: "no-store",
      signal: request.signal,
    }
  );

  if (!upstream.ok || !upstream.body) {
    return Response.json(
      { error: `Stream not available: ${key}` },
      { status: upstream.status }
    );
  }

  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
