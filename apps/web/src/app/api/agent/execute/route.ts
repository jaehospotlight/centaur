/**
 * POST /api/agent/execute
 *
 * Accepts { slack_thread_key, message, harness? } from the client.
 * Calls the Python pipe server, reads raw harness SSE events, converts them
 * to AI SDK v6 UIMessageChunk objects server-side, and returns a proper
 * AI SDK UIMessage stream response.
 *
 * The client can consume this with DefaultChatTransport / HttpChatTransport
 * — no custom SSE parsing needed on the client side.
 */

import { z } from "zod";
import {
  createUIMessageStreamResponse,
  createUIMessageStream,
  createIdGenerator,
  parseJsonEventStream,
} from "ai";
import type { UIMessage } from "ai";
import type { PoolClient } from "pg";
import { resilientFetch, API_URL, ApiError } from "@/lib/api-client";
import {
  canonicalEventToStreamChunks,
  createConversionState,
} from "@/lib/harness-to-ui-chunks";
import { normalizeHarnessEvent } from "@/lib/normalize-harness-event";
import { getPool } from "@/lib/db";

const generateMessageId = createIdGenerator({ prefix: "msg", size: 16 });

export const dynamic = "force-dynamic";
export const fetchCache = "force-no-store";
export const maxDuration = 300;

const rawEventSchema = z.record(z.string(), z.unknown());

type PersistableMessage = {
  id: string;
  role: string;
  parts: unknown[];
  metadata?: Record<string, unknown> | null;
};

type EagerPersistResult = {
  inserted: boolean;
};

async function upsertChatMessages(
  client: PoolClient,
  threadKey: string,
  messages: PersistableMessage[],
  harness: string,
  engine: string | null = null,
  startedAtMs = Date.now(),
) {
  for (let i = 0; i < messages.length; i += 1) {
    const msg = messages[i];
    const ts = new Date(startedAtMs + i).toISOString();
    const metadata = {
      harness,
      ...(engine ? { engine } : {}),
      ...(msg.metadata || {}),
    };
    await client.query(
      `INSERT INTO chat_messages (id, thread_key, role, parts, metadata, created_at)
       VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6::timestamptz)
       ON CONFLICT (id) DO UPDATE SET parts = $4::jsonb, metadata = $5::jsonb`,
      [
        msg.id,
        threadKey,
        msg.role,
        JSON.stringify(msg.parts),
        JSON.stringify(metadata),
        ts,
      ],
    );
  }
}

function extractUsageDataFromChunk(chunk: Record<string, unknown>): Record<string, unknown> | null {
  if (chunk.type !== "data-token-usage") return null;
  const data = chunk.data;
  return data && typeof data === "object" ? (data as Record<string, unknown>) : null;
}

function lastUserMessage(
  messages: UIMessage[],
  fallbackText: string,
): PersistableMessage {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const msg = messages[i];
    if (msg.role !== "user" || !Array.isArray(msg.parts)) continue;
    return {
      id: msg.id,
      role: msg.role,
      parts: msg.parts,
      metadata: {
        source: "thread_ui",
        ...(msg.metadata && typeof msg.metadata === "object"
          ? (msg.metadata as Record<string, unknown>)
          : {}),
      },
    };
  }

  return {
    id: generateMessageId(),
    role: "user",
    parts: [{ type: "text", text: fallbackText }],
    metadata: { source: "thread_ui" },
  };
}

async function persistInitialUserMessage(
  threadKey: string,
  message: PersistableMessage,
  harness: string,
  engine: string | null = null,
): Promise<EagerPersistResult> {
  const pool = getPool();
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    const existing = await client.query<{ exists: boolean }>(
      "SELECT EXISTS(SELECT 1 FROM chat_messages WHERE id = $1) AS exists",
      [message.id],
    );
    const inserted = !existing.rows[0]?.exists;
    await upsertChatMessages(client, threadKey, [message], harness, engine);
    await client.query("COMMIT");
    return { inserted };
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally {
    client.release();
  }
}

async function cleanupInitialUserMessage(
  threadKey: string,
  messageId: string,
  inserted: boolean,
) {
  if (!inserted) return;
  try {
    const pool = getPool();
    await pool.query("DELETE FROM chat_messages WHERE thread_key = $1 AND id = $2", [
      threadKey,
      messageId,
    ]);
  } catch (error) {
    console.warn("Failed to clean up eager persisted message", error);
  }
}

export async function POST(request: Request) {
  const body = await request.json().catch(() => ({}));
  const slackThreadKey = String(body.slack_thread_key ?? "").trim();
  const message = String(body.message ?? "").trim();
  const harness =
    typeof body.harness === "string" && body.harness.trim().length > 0
      ? body.harness.trim()
      : "amp";
  const engine =
    typeof body.engine === "string" && body.engine.trim().length > 0
      ? body.engine.trim()
      : "";
  const originalMessages: UIMessage[] = Array.isArray(body.messages) ? body.messages : [];

  if (!slackThreadKey || !message) {
    return Response.json(
      { error: "Missing slack_thread_key or message" },
      { status: 400, headers: { "Cache-Control": "no-store" } },
    );
  }

  const initialUserMessage = lastUserMessage(originalMessages, message);
  let eagerPersistInserted = false;
  try {
    const result = await persistInitialUserMessage(
      slackThreadKey,
      initialUserMessage,
      harness,
      engine || null,
    );
    eagerPersistInserted = result.inserted;
  } catch (error) {
    console.warn("Initial user message persistence failed; continuing run", error);
  }

  let upstream: Response;
  try {
    upstream = await resilientFetch(`${API_URL}/agent/execute`, {
      method: "POST",
      body: JSON.stringify({
        thread_key: slackThreadKey,
        message,
        harness,
        ...(engine ? { engine } : {}),
      }),
      stream: true,
    });
  } catch (err) {
    await cleanupInitialUserMessage(
      slackThreadKey,
      initialUserMessage.id,
      eagerPersistInserted,
    );
    const status = err instanceof ApiError ? (err.status ?? 502) : 502;
    return Response.json(
      { error: err instanceof Error ? err.message : "API unreachable" },
      { status, headers: { "Cache-Control": "no-store" } },
    );
  }

  if (!upstream.ok) {
    await cleanupInitialUserMessage(
      slackThreadKey,
      initialUserMessage.id,
      eagerPersistInserted,
    );
    const text = await upstream.text().catch(() => "");
    return Response.json(
      { error: `Execute failed: ${upstream.status}`, detail: text.slice(0, 500) },
      { status: upstream.status, headers: { "Cache-Control": "no-store" } },
    );
  }

  if (!upstream.body) {
    await cleanupInitialUserMessage(
      slackThreadKey,
      initialUserMessage.id,
      eagerPersistInserted,
    );
    return Response.json(
      { error: "No response body from pipe server" },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }

  // Parse the raw SSE from the pipe server using the AI SDK's built-in parser
  const rawEvents = parseJsonEventStream({
    stream: upstream.body,
    schema: rawEventSchema,
  });

  // Convert raw harness events → AI SDK UIMessageChunks
  let eventIndex = 0;
  const conversionState = createConversionState();
  let latestTokenUsage: Record<string, unknown> | null = null;

  const uiChunkStream = rawEvents.pipeThrough(
    new TransformStream({
      transform(parseResult, controller) {
        if (!parseResult.success) {
          // Skip malformed events — keep stream alive
          return;
        }
        const rawEvent = parseResult.value;
        const canonicalEvents = normalizeHarnessEvent(harness, rawEvent);
        const chunks = canonicalEvents.flatMap((event, offset) =>
          canonicalEventToStreamChunks(
            0,
            eventIndex + offset,
            event,
            conversionState,
          ),
        );
        eventIndex += Math.max(1, canonicalEvents.length);
        for (const chunk of chunks) {
          const usageData = extractUsageDataFromChunk(chunk);
          if (usageData) {
            latestTokenUsage = usageData;
          }
          controller.enqueue(chunk);
        }
      },
    }),
  );

  // Return a proper AI SDK UIMessage stream response
  return createUIMessageStreamResponse({
    stream: createUIMessageStream({
      originalMessages,
      generateId: generateMessageId,
      execute: async ({ writer }) => {
        writer.merge(uiChunkStream);
      },
      onFinish: async ({ messages }) => {
        try {
          const pool = getPool();
          const client = await pool.connect();
          try {
            await client.query("BEGIN");
            // Preserve chronological ordering with 1ms offsets inside the transaction.
            await upsertChatMessages(
              client,
              slackThreadKey,
              messages.map((msg, index) => {
                const baseMetadata =
                  msg.metadata && typeof msg.metadata === "object"
                    ? (msg.metadata as Record<string, unknown>)
                    : {};
                const shouldAttachUsage =
                  msg.role === "assistant" &&
                  latestTokenUsage &&
                  index === messages.length - 1;
                return {
                  id: msg.id,
                  role: msg.role,
                  parts: Array.isArray(msg.parts) ? msg.parts : [],
                  metadata: shouldAttachUsage
                    ? { ...baseMetadata, token_usage: latestTokenUsage }
                    : baseMetadata,
                };
              }),
              harness,
              engine || null,
            );
            await client.query("COMMIT");
          } catch (e) {
            await client.query("ROLLBACK");
            throw e;
          } finally {
            client.release();
          }
        } catch {
          // Best-effort persistence — don't block stream
        }
      },
    }),
  });
}
