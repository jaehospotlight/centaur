/**
 * Chat SDK bot — Slack adapter with Redis state.
 *
 * On @mention:
 *   1. spawn() → ensures a Docker container exists for this thread
 *   2. execute() → runs the message through the harness CLI
 *   3. thread.post() → posts the result back to Slack
 */

import { Chat } from "chat";
import { createSlackAdapter } from "@chat-adapter/slack";
import { createRedisState } from "@chat-adapter/state-redis";
import { createMemoryState } from "@chat-adapter/state-memory";
import { extractHarness, spawn, execute } from "./harness";

function createBot() {
  const hasSlackCreds =
    process.env.SLACK_BOT_TOKEN && process.env.SLACK_SIGNING_SECRET;

  const bot = new Chat({
    userName: "tempo-ai",
    adapters: hasSlackCreds ? { slack: createSlackAdapter() } : {},
    state: process.env.REDIS_URL ? createRedisState() : createMemoryState(),
  });

  async function handleMessage(
    thread: Parameters<Parameters<typeof bot.onNewMention>[0]>[0],
    messageText: string
  ) {
    const { harness, cleanedText } = extractHarness(messageText);
    const threadKey = thread.id;

    await thread.startTyping("Spawning agent...");

    // Ensure container exists for this thread
    await spawn(threadKey, harness);

    await thread.startTyping("Running...");

    // Execute message and get final result
    const result = await execute(threadKey, cleanedText);

    await thread.post(result);
  }

  // First @mention — subscribe and run
  bot.onNewMention(async (thread, message) => {
    await thread.subscribe();
    await handleMessage(thread, message.text);
  });

  // Follow-up messages in subscribed threads
  bot.onSubscribedMessage(async (thread, message) => {
    if (!message.isMention) return;
    await handleMessage(thread, message.text);
  });

  return bot;
}

let _bot: ReturnType<typeof createBot> | null = null;
export function getBot() {
  if (!_bot) _bot = createBot();
  return _bot;
}
