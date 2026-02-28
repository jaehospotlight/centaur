/** Proxy /api/threads → FastAPI /api/threads */

const API_URL = process.env.AI_V2_API_URL || "http://api:8000";
const API_KEY = process.env.AI_V2_API_KEY || "";

export const dynamic = "force-dynamic";
export const fetchCache = "force-no-store";

export async function GET(request: Request) {
  const res = await fetch(`${API_URL}/api/threads`, {
    headers: { Authorization: `Bearer ${API_KEY}` },
    cache: "no-store",
    signal: request.signal,
  });

  if (!res.ok) {
    return Response.json(
      { error: `Failed to fetch threads: ${res.status}` },
      { status: res.status, headers: { "Cache-Control": "no-store" } }
    );
  }

  const data = await res.json();
  return Response.json(data, { headers: { "Cache-Control": "no-store" } });
}
