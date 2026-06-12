# @centaur/ai-sdk

A Vercel AI SDK agent loop served as a Centaur **harness** — a fourth entry
next to Codex, Claude Code, and Amp in `crates/harness-server`:

```
harness-server ai-sdk --mode jsonrpc
        │  spawns (AISDK_BRIDGE_BIN / CENTAUR_AISDK_BRIDGE_COMMAND)
        ▼
centaur-aisdk-bridge (this package)        ── streamText() agent loop, tools,
        │  stdout: claude-CLI stream-json      steering between steps
        ▼
any AI SDK model/provider
```

Everything above the harness layer (api-rs, Slack, workflows, the SSE event
stream) gets AI SDK agents as a selectable `harness=ai-sdk` value with zero
changes: the bridge emits the same stream-json dialect the Claude Code
harness produces, so the Rust side reuses the existing Anthropic event
normalizer wholesale (`crates/harness-server/src/aisdk.rs`).

## What the bridge does

- Runs a hand-rolled agent loop (`streamText` with `stopWhen: stepCountIs(1)`
  per step) so steered user input injected via `turn/steer` is picked up
  between steps, matching the other harnesses' steering semantics.
- Streams text and reasoning deltas as raw `stream_event` lines; closes each
  step with a full `assistant` message whose `stop_reason` (`tool_use` /
  `end_turn`) drives the commentary vs final-answer phase split downstream.
- Ships a default toolset: `Bash` (named so harness-server projects it to
  first-class `commandExecution` items, like Claude Code's shell runs) and
  `ReadFile` (projected as a `dynamicToolCall`).
- Keeps conversation history in process memory across turns; the harness
  child stays alive for the thread's lifetime (`--session-id` / `--resume`
  flags mirror the Claude harness contract).

## Configuration

| Env | Meaning |
| --- | --- |
| `AISDK_MODEL` / `--model` | Model id (default `claude-sonnet-4-6`; `mock` runs a scripted offline model) |
| `ANTHROPIC_API_KEY` | Auth for the default `@ai-sdk/anthropic` provider |
| `AISDK_BRIDGE_BIN` | Bridge binary for `harness-server` to spawn (default `centaur-aisdk-bridge`) |
| `CENTAUR_AISDK_BRIDGE_COMMAND` | Full shell-command override (dev: `node .../src/bridge.ts ...`) |

Other providers: swap `resolveModel` in `src/bridge.ts` (anything that
returns an AI SDK `LanguageModel` works — including, recursively, Vercel's
own experimental harness adapters).

## Tests

- `pnpm test` — bridge agent loop against `MockLanguageModelV3` (scripted
  tool-call + answer scenario, error surfacing).
- `node test/e2e-jsonrpc.mjs <harness-server-bin>` — offline end-to-end:
  JSON-RPC client → Rust server → bridge with the mock model, asserting the
  normalized turn contains a `commandExecution` item and a `final_answer`
  agent message.
- `cargo test -p harness-server` covers the Rust-side adapter
  (`aisdk::tests`).
