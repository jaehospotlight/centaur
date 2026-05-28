import { createHmac } from 'node:crypto'
import { afterEach, describe, expect, it, mock } from 'bun:test'

const originalEnv = { ...process.env }

afterEach(() => {
  for (const key of Object.keys(process.env)) {
    if (!(key in originalEnv)) delete process.env[key]
  }
  Object.assign(process.env, originalEnv)
})

describe('Slack Chat SDK webhook', () => {
  it('creates Linear issues from configured feedback slash commands', async () => {
    process.env.SLACK_SIGNING_SECRET = 'test-signing-secret'
    process.env.SLACK_BOT_TOKEN = 'xoxb-test'
    const slackMethods: string[] = []
    const slackServer = Bun.serve({
      port: 0,
      async fetch(request: Request) {
        const url = new URL(request.url)
        slackMethods.push(url.pathname)
        if (url.pathname.endsWith('/auth.test')) {
          return jsonResponse({ ok: true, user_id: 'UBOT', bot_id: 'BBOT', user: 'centaur' })
        }
        return jsonResponse({ ok: true, channel: 'C123', message_ts: '1778883099.579529' })
      }
    })

    process.env.SLACK_API_URL = `http://localhost:${slackServer.port}/api/`
    process.env.LINEAR_API_KEY = 'lin-test-key'
    process.env.SLACK_FEEDBACK_LINEAR_TEAM_ID = 'team-feedback'
    process.env.SLACK_FEEDBACK_LINEAR_PROJECT_ID = 'project-feedback'

    const originalFetch = globalThis.fetch
    const fetchMock = mock(async (input: string | URL | Request, init?: RequestInit) => {
      const url = new URL(input instanceof Request ? input.url : input)
      if (url.hostname !== 'api.linear.app') return originalFetch(input as Request, init)

      const body = JSON.parse(init?.body as string) as {
        variables: { input: { title: string; teamId: string; projectId: string } }
      }
      expect(body.variables.input).toMatchObject({
        title: 'Button copy is confusing',
        teamId: 'team-feedback',
        projectId: 'project-feedback'
      })
      return jsonResponse({
        data: {
          issueCreate: {
            issue: {
              identifier: 'DSGN-123',
              url: 'https://linear.app/paradigmxyz/issue/DSGN-123'
            }
          }
        }
      })
    })
    globalThis.fetch = fetchMock as unknown as typeof fetch

    try {
      const { app } = await import('./index')
      const body = new URLSearchParams({
        command: '/website-feedback',
        text: 'Button copy is confusing\nThe submit button should mention Linear.',
        team_id: 'T123',
        user_id: 'U123',
        channel_id: 'C123',
        channel_name: 'design-feedback'
      }).toString()
      const waits: Promise<unknown>[] = []

      const response = await app.request(
        '/api/slack/commands',
        signedFormRequest(body, process.env.SLACK_SIGNING_SECRET),
        {},
        waitUntilContext(waits)
      )

      expect(response.status).toBe(200)
      expect(await response.text()).toBe('')
      await Promise.all(waits)
      expect(fetchMock).toHaveBeenCalled()
      expect(slackMethods).toContain('/api/auth.test')
      expect(slackMethods).toContain('/api/chat.postEphemeral')
    } finally {
      globalThis.fetch = originalFetch
      await slackServer.stop()
    }
  })
})

function signedFormRequest(body: string, signingSecret: string): RequestInit {
  const timestamp = Math.floor(Date.now() / 1000).toString()
  const signature = `v0=${createHmac('sha256', signingSecret)
    .update(`v0:${timestamp}:${body}`)
    .digest('hex')}`
  return {
    method: 'POST',
    headers: {
      'content-type': 'application/x-www-form-urlencoded',
      'x-slack-request-timestamp': timestamp,
      'x-slack-signature': signature
    },
    body
  }
}

function waitUntilContext(waits: Promise<unknown>[]): any {
  return {
    waitUntil: (promise: Promise<unknown>) => waits.push(promise),
    passThroughOnException: () => {},
    props: {}
  }
}

function jsonResponse(body: Record<string, unknown>): Response {
  return new Response(JSON.stringify(body), {
    headers: {
      'content-type': 'application/json'
    }
  })
}
