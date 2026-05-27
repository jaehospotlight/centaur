import type { MarkdownBlock } from '@slack/types'
import { slackReplyLimits } from '../constants'
import type { SlackBlock } from './block-kit'
import { enforceBlockLimits } from './render'

const MARKDOWN_CUMULATIVE_CHARS = slackReplyLimits.stream.markdownChunkChars
const PAYLOAD_BYTE_BUDGET = slackReplyLimits.mixedBodyAndPlan.maxPayloadBytes
const MAX_FALLBACK_CHARS = slackReplyLimits.text.maxFallbackChars

export function buildFinalFallbackText(opts: { title: string; answerMarkdown: string }): string {
  const parts = [opts.title.trim(), opts.answerMarkdown.trim()].filter(Boolean)
  const text = parts.join('\n')
  if (!text) return opts.title.trim() || 'Centaur update'
  if (text.length <= MAX_FALLBACK_CHARS) return text
  return `${text.slice(0, MAX_FALLBACK_CHARS - 1)}…`
}

/** Enforce Slack limits on the composed chat.update payload (plan + markdown + footer). */
export function sanitizeFinalMessagePayload(blocks: SlackBlock[]): SlackBlock[] {
  let sanitized = enforceBlockLimits(blocks)
  sanitized = capMarkdownBlocksCumulative(sanitized, MARKDOWN_CUMULATIVE_CHARS)
  sanitized = shrinkToPayloadByteBudget(sanitized, PAYLOAD_BYTE_BUDGET)
  return sanitized
}

function capMarkdownBlocksCumulative(blocks: SlackBlock[], maxChars: number): SlackBlock[] {
  let total = markdownCharsUsed(blocks)
  if (total <= maxChars) return blocks

  const out = blocks.map(block => ({ ...block })) as SlackBlock[]
  for (let index = out.length - 1; index >= 0 && total > maxChars; index -= 1) {
    const block = out[index]
    if (block?.type !== 'markdown') continue
    const markdown = block as MarkdownBlock
    const overflow = total - maxChars
    const nextLength = Math.max(0, markdown.text.length - overflow)
    const trimmed = markdown.text.slice(0, nextLength).trimEnd()
    markdown.text = trimmed || ' '
    total = markdownCharsUsed(out)
  }
  return out
}

function shrinkToPayloadByteBudget(blocks: SlackBlock[], maxBytes: number): SlackBlock[] {
  let sanitized = blocks
  if (estimatePayloadBytes(sanitized) <= maxBytes) return sanitized

  sanitized = trimPlanTasks(stripPlanTaskBodies(sanitized), 0)
  const bytes = estimatePayloadBytes(sanitized)
  if (bytes <= maxBytes) return sanitized

  return blocks.filter(block => block.type === 'markdown') as SlackBlock[]
}

function stripPlanTaskBodies(blocks: SlackBlock[]): SlackBlock[] {
  return blocks.map(block => {
    if (block.type !== 'plan' || !('tasks' in block) || !Array.isArray(block.tasks)) {
      return block
    }
    return {
      ...block,
      tasks: block.tasks.map(task => ({
        ...task,
        details: undefined,
        output: undefined
      }))
    }
  })
}

function trimPlanTasks(blocks: SlackBlock[], maxTasks: number): SlackBlock[] {
  return blocks.map(block => {
    if (block.type !== 'plan' || !('tasks' in block) || !Array.isArray(block.tasks)) {
      return block
    }
    return {
      ...block,
      tasks: block.tasks.slice(0, maxTasks)
    }
  }) as SlackBlock[]
}

function markdownCharsUsed(blocks: SlackBlock[]): number {
  return blocks.reduce((total, block) => {
    if (block.type !== 'markdown') return total
    return total + (block as MarkdownBlock).text.length
  }, 0)
}

export function estimatePayloadBytes(blocks: SlackBlock[]): number {
  return Buffer.byteLength(JSON.stringify(blocks), 'utf8')
}
