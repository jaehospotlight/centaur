import { CentaurClient, type ChatStreamChunk, type WorkflowRunAccepted } from '@centaur/api-client'
import type { SlackAdapter } from '@chat-adapter/slack'
import type { StreamOptions } from 'chat'
import { centaurApiKey, type AppConfig } from '../config'
import { logInfo, logWarn } from '../logging'

const WORKFLOW_EXECUTION_WAIT_MS = 5 * 60 * 1000
const WORKFLOW_EXECUTION_POLL_MS = 500

export type ChatSdkRenderInput = {
  runId: string
  config: AppConfig
  adapter: SlackAdapter
}

export function workflowRunIdFromBody(body: unknown): string | null {
  if (!body || typeof body !== 'object') return null
  const runId = (body as { run_id?: unknown }).run_id
  return typeof runId === 'string' && runId.trim() ? runId.trim() : null
}

export function steeredExecutionIdFromBody(body: unknown): string | null {
  if (!body || typeof body !== 'object') return null
  const record = body as { steered?: unknown; execution_id?: unknown }
  if (record.steered !== true) return null
  const executionId = record.execution_id
  return typeof executionId === 'string' && executionId.trim() ? executionId.trim() : null
}

export async function renderWorkflowRunWithChatSdk(input: ChatSdkRenderInput): Promise<void> {
  const apiKey = centaurApiKey(input.config)
  if (!apiKey) {
    throw new Error('CENTAUR_API_KEY is required for Chat SDK rendering')
  }

  const api = new CentaurClient({
    apiUrl: input.config.CENTAUR_API_URL,
    apiKey
  })
  const executionId = await waitForExecutionId(api, input.runId)
  let threadId: string | null = null

  try {
    const context = await api.getChatStreamContext(executionId)
    threadId = requiredString(context.thread_id, 'chat stream context thread_id')
    const streamOptions = chatSdkStreamOptions(context.stream_options)
    logInfo('chat_sdk_stream_started', {
      workflow_run_id: input.runId,
      execution_id: executionId,
      thread_id: threadId,
      platform: context.platform
    })
    try {
      const stream = await requireFirstChunk(api.streamChatChunks({ executionId }))
      await input.adapter.stream(threadId, stream, streamOptions)
    } catch (streamError) {
      await postTerminalResultFallback({
        api,
        adapter: input.adapter,
        executionId,
        threadId,
        streamError
      })
      await api.markFinalDelivered(executionId)
      logInfo('chat_sdk_stream_fallback_completed', {
        workflow_run_id: input.runId,
        execution_id: executionId,
        thread_id: threadId
      })
      return
    }
    await api.markFinalDelivered(executionId)
    logInfo('chat_sdk_stream_completed', {
      workflow_run_id: input.runId,
      execution_id: executionId,
      thread_id: threadId
    })
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    logWarn('chat_sdk_stream_failed', {
      workflow_run_id: input.runId,
      execution_id: executionId,
      thread_id: threadId,
      error: message
    })
    await api.markFinalFailed(executionId, message, {
      retryAfterSeconds: 60
    })
    throw error
  }
}

export async function postTerminalResultFallback(input: {
  api: Pick<CentaurClient, 'getExecution'>
  adapter: Pick<SlackAdapter, 'postMessage'>
  executionId: string
  threadId: string
  streamError: unknown
}): Promise<void> {
  const streamErrorMessage =
    input.streamError instanceof Error ? input.streamError.message : String(input.streamError)
  logWarn('chat_sdk_stream_using_terminal_post_fallback', {
    execution_id: input.executionId,
    thread_id: input.threadId,
    error: streamErrorMessage
  })
  const execution = await input.api.getExecution(input.executionId)
  const resultText = stringValue(execution.result_text)
  if (!resultText) {
    throw new Error(`Chat SDK stream failed and execution ${input.executionId} has no result_text`)
  }
  await input.adapter.postMessage(input.threadId, resultText)
}

export async function requireFirstChunk(
  source: AsyncIterable<ChatStreamChunk>
): Promise<AsyncIterable<ChatStreamChunk>> {
  const iterator = source[Symbol.asyncIterator]()
  const first = await iterator.next()
  if (!first.done) {
    return prependAsyncIterable(first.value, iterator)
  }
  throw new Error('Chat SDK stream produced no chunks')
}

async function* prependAsyncIterable<T>(
  first: T,
  iterator: AsyncIterator<T>
): AsyncGenerator<T, void, undefined> {
  yield first
  while (true) {
    const next = await iterator.next()
    if (next.done) return
    yield next.value
  }
}

async function waitForExecutionId(api: CentaurClient, runId: string): Promise<string> {
  const deadline = Date.now() + WORKFLOW_EXECUTION_WAIT_MS
  let latest: WorkflowRunAccepted | null = null
  while (Date.now() < deadline) {
    latest = await api.getWorkflowRun(runId)
    const executionId = stringValue(latest.execution_id)
    if (executionId) return executionId
    const waitingExecutionId = stringValue(latest.waiting_on?.execution_id)
    if (waitingExecutionId) return waitingExecutionId
    if (isTerminalWorkflowStatus(latest.status)) {
      throw new Error(
        `Workflow ${runId} reached ${latest.status} without an execution_id: ${latest.error_text ?? ''}`
      )
    }
    await delay(WORKFLOW_EXECUTION_POLL_MS)
  }
  throw new Error(
    `Timed out waiting for execution_id for workflow ${runId}; latest status ${latest?.status ?? 'unknown'}`
  )
}

function chatSdkStreamOptions(apiOptions: StreamOptions | undefined): StreamOptions {
  const options: StreamOptions = { ...apiOptions }
  options.recipientUserId = requiredString(
    options.recipientUserId,
    'chat stream context stream_options.recipientUserId'
  )
  options.recipientTeamId = requiredString(
    options.recipientTeamId,
    'chat stream context stream_options.recipientTeamId'
  )
  options.taskDisplayMode ??= 'plan'
  return options
}

function isTerminalWorkflowStatus(status: string | undefined): boolean {
  return status === 'completed' || status === 'failed' || status === 'cancelled'
}

function stringValue(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function requiredString(value: unknown, name: string): string {
  const normalized = stringValue(value)
  if (!normalized) throw new Error(`${name} is required`)
  return normalized
}

function delay(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms))
}
