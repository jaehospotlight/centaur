import { resilientFetch, API_URL, ApiError } from "@/lib/api-client";
import { normalizeThreadStateValue } from "@/lib/viewer/thread-runtime";

export const dynamic = "force-dynamic";
export const fetchCache = "force-no-store";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const key = searchParams.get("key")?.trim() || "";
  if (!key) {
    return Response.json(
      { error: "Missing thread key" },
      { status: 400, headers: { "Cache-Control": "no-store" } },
    );
  }

  try {
    const upstream = await resilientFetch(`${API_URL}/agent/status?key=${encodeURIComponent(key)}`, {
      timeoutMs: 5_000,
      signal: request.signal,
      maxAttempts: 1,
    });
    const data = (await upstream.json().catch(() => ({}))) as Record<string, unknown>;
    const state = normalizeThreadStateValue(data.status);
    return Response.json(
      {
        ...data,
        ...(state ? { state } : {}),
      },
      {
      status: upstream.ok ? 200 : upstream.status,
      headers: { "Cache-Control": "no-store" },
      },
    );
  } catch (err) {
    const status = err instanceof ApiError ? (err.status ?? 502) : 502;
    return Response.json(
      { error: err instanceof Error ? err.message : "API unreachable" },
      { status, headers: { "Cache-Control": "no-store" } },
    );
  }
}
