/** Proxy POST /api/agent/interrupt → FastAPI /agent/interrupt */

const API_URL = process.env.AI_V2_API_URL || "http://api:8000";
const API_KEY = process.env.AI_V2_API_KEY || "";

export const dynamic = "force-dynamic";
export const fetchCache = "force-no-store";

export async function POST(request: Request) {
  const body = await request.json().catch(() => ({}));
  const slackThreadKey = String(body.slack_thread_key ?? "").trim();
  if (!slackThreadKey) {
    return Response.json(
      { error: "Missing slack_thread_key" },
      { status: 400, headers: { "Cache-Control": "no-store" } }
    );
  }

  const upstream = await fetch(`${API_URL}/agent/interrupt`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ slack_thread_key: slackThreadKey }),
    cache: "no-store",
    signal: request.signal,
  });

  const text = await upstream.text();
  if (!upstream.ok) {
    return Response.json(
      { error: `Interrupt failed: ${upstream.status}`, detail: text.slice(0, 500) },
      { status: upstream.status, headers: { "Cache-Control": "no-store" } }
    );
  }

  try {
    return Response.json(JSON.parse(text), { headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ status: "ok" }, { headers: { "Cache-Control": "no-store" } });
  }
}
