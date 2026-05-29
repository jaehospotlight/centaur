import { describe, expect, it, mock } from 'bun:test'
import type { ChatStreamChunk } from '@centaur/api-client'
import { postTerminalResultFallback, requireFirstChunk } from './chat-sdk-renderer'

describe('Chat SDK renderer stream preparation', () => {
  it('preserves API chunks when the stream has content', async () => {
    const chunks: ChatStreamChunk[] = [
      { type: 'markdown_text', text: '_base · codex_\n\n' },
      { type: 'markdown_text', text: 'PONG' }
    ]

    const prepared = await requireFirstChunk(asyncIterable(chunks))

    expect(await collect(prepared)).toEqual(chunks)
  })

  it('rejects an empty API stream', async () => {
    let error: unknown
    try {
      await requireFirstChunk(asyncIterable([]))
    } catch (caught) {
      error = caught
    }

    expect(error).toBeInstanceOf(Error)
    expect((error as Error).message).toBe('Chat SDK stream produced no chunks')
  })
})

describe('Chat SDK renderer terminal fallback', () => {
  it('posts terminal result text when Slack native streaming fails', async () => {
    const getExecution = mock(async () => ({ result_text: 'final answer' }))
    const postMessage = mock(async () => ({ id: '1780000000.000001' }))

    await postTerminalResultFallback({
      api: { getExecution },
      adapter: { postMessage } as any,
      executionId: 'exe-123',
      threadId: 'slack:C123:1780000000.000000',
      streamError: new Error('An API error occurred: restricted_action')
    })

    expect(getExecution).toHaveBeenCalledWith('exe-123')
    expect(postMessage).toHaveBeenCalledWith('slack:C123:1780000000.000000', 'final answer')
  })

  it('rejects fallback when the terminal execution has no result text', async () => {
    const getExecution = mock(async () => ({ result_text: '' }))
    const postMessage = mock(async () => ({ id: 'unused' }))
    let error: unknown

    try {
      await postTerminalResultFallback({
        api: { getExecution },
        adapter: { postMessage } as any,
        executionId: 'exe-empty',
        threadId: 'slack:C123:1780000000.000000',
        streamError: new Error('boom')
      })
    } catch (caught) {
      error = caught
    }

    expect(error).toBeInstanceOf(Error)
    expect((error as Error).message).toContain('has no result_text')
    expect(postMessage).not.toHaveBeenCalled()
  })
})

async function* asyncIterable<T>(items: T[]): AsyncGenerator<T, void, undefined> {
  for (const item of items) yield item
}

async function collect<T>(items: AsyncIterable<T>): Promise<T[]> {
  const out: T[] = []
  for await (const item of items) out.push(item)
  return out
}
