import { createHmac } from 'node:crypto'
import { afterEach, describe, expect, it, mock } from 'bun:test'

const originalEnv = { ...process.env }

afterEach(() => {
  for (const key of Object.keys(process.env)) {
    if (!(key in originalEnv)) delete process.env[key]
  }
  Object.assign(process.env, originalEnv)
})

describe('Gmail OAuth Slack surfaces', () => {
  it('returns ephemeral Gmail status without public posting', async () => {
    process.env.SLACK_SIGNING_SECRET = 'test-signing-secret'
    process.env.SLACKBOT_API_KEY = 'slackbot-key'
    process.env.CENTAUR_API_URL = 'https://centaur.test'

    const originalFetch = globalThis.fetch
    globalThis.fetch = mock(async (input: string | URL | Request) => {
      expect(new URL(String(input)).pathname).toBe('/internal/gmail-oauth/status')
      return new Response(JSON.stringify({ state: 'connection_invalid', email: 'user@example.com' }), {
        status: 200
      })
    }) as unknown as typeof fetch

    try {
      const { app } = await import('./index')
      const body = new URLSearchParams({
        command: '/ai-email-status',
        user_id: 'U123',
        team_id: 'T123',
        channel_id: 'C123'
      }).toString()

      const response = await app.request(
        '/api/slack/commands',
        signedFormRequest(body, process.env.SLACK_SIGNING_SECRET)
      )

      expect(response.status).toBe(200)
      expect(await response.json()).toEqual({
        response_type: 'ephemeral',
        text: 'Gmail connection invalid for user@example.com. Run /ai-email-connect again.'
      })
    } finally {
      globalThis.fetch = originalFetch
    }
  })

  it('returns ephemeral Gmail connect prompt with pairing code', async () => {
    process.env.SLACK_SIGNING_SECRET = 'test-signing-secret'
    process.env.SLACKBOT_API_KEY = 'slackbot-key'
    process.env.CENTAUR_API_URL = 'https://centaur.test'

    const originalFetch = globalThis.fetch
    globalThis.fetch = mock(async () => {
      return new Response(JSON.stringify({ pairing_code: 'ABC-123', pairing_token: 'signed-token' }), {
        status: 200
      })
    }) as unknown as typeof fetch

    try {
      const { app } = await import('./index')
      const body = new URLSearchParams({
        command: '/ai-email-connect',
        user_id: 'U123',
        team_id: 'T123',
        channel_id: 'C123'
      }).toString()

      const response = await app.request(
        '/api/slack/commands',
        signedFormRequest(body, process.env.SLACK_SIGNING_SECRET)
      )
      const json = (await response.json()) as { response_type: string; text: string; blocks: unknown }

      expect(response.status).toBe(200)
      expect(json.response_type).toBe('ephemeral')
      expect(json.text).toContain('Pairing code: ABC-123')
      expect(JSON.stringify(json.blocks)).toContain('gmail_begin_connection')
    } finally {
      globalThis.fetch = originalFetch
    }
  })
})

function signedFormRequest(body: string, secret: string): RequestInit {
  const timestamp = Math.floor(Date.now() / 1000).toString()
  const signatureBase = `v0:${timestamp}:${body}`
  const signature = `v0=${createHmac('sha256', secret).update(signatureBase).digest('hex')}`
  return {
    method: 'POST',
    body,
    headers: {
      'content-type': 'application/x-www-form-urlencoded',
      'x-slack-request-timestamp': timestamp,
      'x-slack-signature': signature
    }
  }
}
