import { afterEach, describe, expect, test } from 'bun:test'
import type { Logger, Message } from 'chat'
import { isAllowedSlackMessage, isAllowedSlackWebhookBody } from '../src/slack-events'
import type { SlackbotV2Options } from '../src/types'

const logger = (): Logger => {
  const records: Array<{ event: string; data?: unknown }> = []
  const item: Logger = {
    debug: () => undefined,
    info: () => undefined,
    warn: (event: string, data?: unknown) => records.push({ data, event }),
    error: () => undefined,
    child: () => item
  }
  return Object.assign(item, { records })
}

describe('Slack event policy', () => {
  afterEach(() => {
    delete process.env.SLACKBOT_DM_TEAM_ALLOWLIST
  })

  test('allows DM events when no DM team allowlist is configured', () => {
    const logs = logger()
    expect(
      isAllowedSlackWebhookBody(slackEvent({ channel: 'D1', team: 'THOST' }), options(), logs)
    ).toBe(true)
  })

  test('rejects DM events from teams outside the configured allowlist', () => {
    const logs = logger()
    expect(
      isAllowedSlackWebhookBody(
        slackEvent({ channel: 'D1', team: 'THOST' }),
        options({ allowedDmTeamIds: ['TOTHER'] }),
        logs
      )
    ).toBe(false)
    expect(logRecords(logs)).toContainEqual(
      expect.objectContaining({ event: 'slackbotv2_dm_ignored_team_not_allowlisted' })
    )
  })

  test('rejects group DM events from teams outside the configured allowlist', () => {
    const logs = logger()
    expect(
      isAllowedSlackWebhookBody(
        slackEvent({ channel: 'G1', channelType: 'mpim', team: 'THOST' }),
        options({ allowedDmTeamIds: ['TOTHER'] }),
        logs
      )
    ).toBe(false)
    expect(logRecords(logs)).toContainEqual(
      expect.objectContaining({ event: 'slackbotv2_dm_ignored_team_not_allowlisted' })
    )
  })

  test('allows DM events from teams in the configured allowlist', () => {
    const logs = logger()
    expect(
      isAllowedSlackWebhookBody(
        slackEvent({ channel: 'D1', team: 'THOST' }),
        options({ allowedDmTeamIds: ['thost'] }),
        logs
      )
    ).toBe(true)
  })

  test('uses the requester team for Slack Connect DMs', () => {
    const logs = logger()
    expect(
      isAllowedSlackWebhookBody(
        slackEvent({ channel: 'D1', team: 'TEXTERNAL', teamId: 'THOST', userTeam: 'TEXTERNAL' }),
        options({ allowedDmTeamIds: ['THOST'], allowedExternalTeamIds: ['TEXTERNAL'] }),
        logs
      )
    ).toBe(false)
    expect(
      isAllowedSlackWebhookBody(
        slackEvent({ channel: 'D1', team: 'TEXTERNAL', teamId: 'THOST', userTeam: 'TEXTERNAL' }),
        options({ allowedDmTeamIds: ['TEXTERNAL'], allowedExternalTeamIds: ['TEXTERNAL'] }),
        logs
      )
    ).toBe(true)
  })

  test('does not apply the DM team allowlist to channel events', () => {
    const logs = logger()
    expect(
      isAllowedSlackWebhookBody(
        slackEvent({ channel: 'C1', team: 'TOTHER' }),
        options({ allowedDmTeamIds: ['THOST'] }),
        logs
      )
    ).toBe(true)
  })

  test('reads the DM team allowlist from the environment', () => {
    process.env.SLACKBOT_DM_TEAM_ALLOWLIST = 'THOST,TOTHER'
    const logs = logger()
    expect(
      isAllowedSlackWebhookBody(slackEvent({ channel: 'D1', team: 'THOST' }), options(), logs)
    ).toBe(true)
  })

  test('applies the DM team allowlist to adapter messages too', () => {
    const logs = logger()
    expect(
      isAllowedSlackMessage(
        slackMessage({ channel: 'D1', team: 'THOST' }),
        options({ allowedDmTeamIds: ['TOTHER'] }),
        logs
      )
    ).toBe(false)
  })

  test('applies the DM team allowlist to adapter group DM messages too', () => {
    const logs = logger()
    expect(
      isAllowedSlackMessage(
        slackMessage({ channel: 'G1', channelType: 'mpim', team: 'THOST' }),
        options({ allowedDmTeamIds: ['TOTHER'] }),
        logs
      )
    ).toBe(false)
  })
})

function slackEvent(input: {
  channel: string
  channelType?: string
  team: string
  teamId?: string
  userTeam?: string
}): string {
  return JSON.stringify({
    type: 'event_callback',
    team_id: input.teamId ?? input.team,
    event_id: 'Ev-test',
    event: {
      type: 'message',
      channel: input.channel,
      channel_type: input.channelType ?? (input.channel.startsWith('D') ? 'im' : 'channel'),
      team: input.team,
      user: 'U1',
      ...(input.userTeam ? { user_team: input.userTeam } : {})
    }
  })
}

function slackMessage(input: { channel: string; channelType?: string; team: string }): Message {
  return {
    author: { isBot: false },
    id: '1710000000.000100',
    raw: {
      type: 'message',
      channel: input.channel,
      channel_type: input.channelType ?? (input.channel.startsWith('D') ? 'im' : 'channel'),
      team: input.team,
      team_id: input.team,
      user: 'U1'
    },
    threadId: `slack:${input.channel}:1710000000.000100`
  } as unknown as Message
}

function options(overrides: Partial<SlackbotV2Options> = {}): SlackbotV2Options {
  return {
    apiUrl: 'http://centaur.test',
    botToken: 'xoxb-test',
    signingSecret: 'secret',
    ...overrides
  }
}

function logRecords(logger: Logger): Array<{ event: string; data?: unknown }> {
  return (logger as Logger & { records: Array<{ event: string; data?: unknown }> }).records
}
