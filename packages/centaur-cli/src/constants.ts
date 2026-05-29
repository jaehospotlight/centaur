export const VERSION = '0.1.0'

export const AUTH_MODES = ['api_key', 'access_token'] as const
export type AuthMode = (typeof AUTH_MODES)[number]

export const HARNESSES = ['codex', 'claude-code'] as const
export type Harness = (typeof HARNESSES)[number]

export const INSTALL_MODES = ['local', 'k3s', 'k8s', 'ssh'] as const
export type InstallMode = (typeof INSTALL_MODES)[number]

export const IMAGE_SOURCES = ['ghcr', 'local'] as const
export type ImageSource = (typeof IMAGE_SOURCES)[number]

export const SECRET_BACKENDS = [
  'local-env',
  'onepassword',
  'onepassword-connect',
  'doppler',
  'vault',
  'sops',
  'kubernetes',
] as const
export type SecretBackend = (typeof SECRET_BACKENDS)[number]

export const CODEX_ACCESS_TOKEN_SECRETS = [
  'OPENAI_CODEX_CLIENT_ID',
  'OPENAI_CODEX_BLOB',
  'OPENAI_CODEX_ACCOUNT_ID',
] as const

export const CLAUDE_ACCESS_TOKEN_SECRETS = [
  'CLAUDE_CODE_CLIENT_ID',
  'CLAUDE_CODE_BLOB',
] as const
