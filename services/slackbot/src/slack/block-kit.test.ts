import { describe, expect, it } from 'bun:test'
import {
  BlockKitValidationError,
  blocksChunk,
  parseSlackBlocks,
  parseSlackStreamChunks
} from './block-kit'

describe('Block Kit validation', () => {
  it('accepts documented markdown, context, rich text, and plan blocks', () => {
    const blocks = parseSlackBlocks([
      { type: 'markdown', text: '**Done**' },
      {
        type: 'context',
        elements: [{ type: 'mrkdwn', text: '*Thinking*\\nChecked local tests.' }]
      },
      {
        type: 'plan',
        title: 'Execution complete',
        tasks: [
          {
            task_id: 'cmd-1',
            title: 'Ran unit tests',
            status: 'complete',
            output: {
              type: 'rich_text',
              elements: [
                {
                  type: 'rich_text_section',
                  elements: [{ type: 'text', text: 'All tests passed' }]
                }
              ]
            }
          }
        ]
      }
    ])

    expect(blocks).toHaveLength(3)
  })

  it('rejects blocks that violate documented required fields and limits', () => {
    expect(() => parseSlackBlocks([{ type: 'section' }])).toThrow(BlockKitValidationError)
    expect(() => parseSlackBlocks([{ type: 'markdown', text: 'x'.repeat(12_001) }])).toThrow(
      'markdown blocks exceed'
    )
    expect(() =>
      parseSlackBlocks([
        {
          type: 'context',
          elements: Array.from({ length: 11 }, () => ({ type: 'mrkdwn', text: 'x' }))
        }
      ])
    ).toThrow('must contain 1 to 10 items')
  })

  it('accepts Slack stream blocks chunks in addition to typed stream chunks', () => {
    const chunks = parseSlackStreamChunks([
      { type: 'plan_update', title: 'Execution' },
      { type: 'task_update', id: 'task-1', title: 'Run command', status: 'in_progress' },
      blocksChunk([{ type: 'section', text: { type: 'mrkdwn', text: 'Section text' } }])
    ])

    expect(chunks.map(chunk => chunk.type)).toEqual(['plan_update', 'task_update', 'blocks'])
  })
})
