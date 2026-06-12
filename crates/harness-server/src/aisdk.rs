use std::env;
use std::process::Command as ProcessCommand;

use codex_app_server_protocol::UserInput;
use serde_json::json;

use crate::anthropic::{AnthropicEventNormalizer, AnthropicStreamEvent};
use crate::traits::{HarnessKind, HarnessServer, NormalizedEvent, ThreadState};
use crate::{Result, command_from_override, user_input_to_anthropic_content};

/// Runs a Vercel AI SDK agent loop as a harness, peer to Codex / Claude Code /
/// Amp. The agent itself lives in a Node bridge (`packages/ai-sdk`) that
/// emits Claude-CLI-compatible stream-json on stdout, so this adapter reuses
/// the Anthropic event normalizer wholesale: the bridge is just another
/// producer of the same wire format the Claude harness already speaks.
pub struct AiSdkHarness;

impl HarnessServer for AiSdkHarness {
    type Event = AnthropicStreamEvent;
    type EventNormalizer = AnthropicEventNormalizer;

    fn kind(&self) -> HarnessKind {
        HarnessKind::AiSdk
    }

    fn cli_version(&self) -> &'static str {
        "ai-sdk"
    }

    /// Empty when no explicit override exists: the bridge owns the default
    /// model (and provider) configuration, mirroring how claude falls through
    /// to settings.json.
    fn default_model(&self) -> String {
        env::var("AISDK_MODEL").unwrap_or_default()
    }

    fn default_model_provider(&self) -> &'static str {
        "ai-sdk"
    }

    fn command_for_turn(&self, state: &ThreadState) -> ProcessCommand {
        if let Some(command) = command_from_override("CENTAUR_AISDK_BRIDGE_COMMAND") {
            return command;
        }

        let bin = env::var("AISDK_BRIDGE_BIN").unwrap_or_else(|_| "centaur-aisdk-bridge".to_string());
        let mut command = ProcessCommand::new(bin);
        if !state.model.is_empty() {
            command.args(["--model", &state.model]);
        }
        if let Some(session_id) = &state.harness_session_id {
            command.args(["--resume", session_id]);
        } else {
            command.args(["--session-id", &state.id]);
        }
        command
    }

    fn stdin_for_turn(&self, input: &[UserInput]) -> Result<Vec<u8>> {
        let payload = json!({
            "type": "user",
            "message": {
                "role": "user",
                "content": user_input_to_anthropic_content(input),
            },
        });
        let mut bytes = serde_json::to_vec(&payload)?;
        bytes.push(b'\n');
        Ok(bytes)
    }

    fn parse_stdout_line(&self, line: &str) -> Result<Self::Event> {
        AnthropicStreamEvent::parse_json_line(line)
    }

    fn normalize_events(
        &self,
        normalizer: &mut Self::EventNormalizer,
        event: Self::Event,
    ) -> Result<Vec<NormalizedEvent>> {
        Ok(vec![normalizer.normalize(event)])
    }
}

#[cfg(test)]
mod tests {
    use codex_app_server_protocol::ServerNotification;
    use serde_json::{Value, json};

    use crate::turn::{BridgeConfig, CodexTurnNormalizer};
    use crate::wire::notification_to_jsonrpc;
    use crate::{HarnessServer, NormalizedEvent};

    use super::{AiSdkHarness, AnthropicEventNormalizer};

    fn feed(
        harness: &AiSdkHarness,
        event_normalizer: &mut AnthropicEventNormalizer,
        turn_normalizer: &mut CodexTurnNormalizer,
        line: Value,
    ) -> Vec<ServerNotification> {
        let event = harness.parse_stdout_line(&line.to_string()).unwrap();
        harness
            .normalize_events(event_normalizer, event)
            .unwrap()
            .into_iter()
            .flat_map(|normalized| turn_normalizer.process_event(&normalized).unwrap())
            .collect()
    }

    #[test]
    fn stdin_for_turn_is_claude_compatible_user_line() {
        let bytes = AiSdkHarness
            .stdin_for_turn(&[codex_app_server_protocol::UserInput::Text {
                text: "hi there".to_string(),
                text_elements: Vec::new(),
            }])
            .unwrap();
        let value: Value = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(value["type"], "user");
        assert_eq!(value["message"]["content"][0]["text"], "hi there");
    }

    #[test]
    fn bridge_stream_lines_normalize_to_app_server_notifications() {
        let harness = AiSdkHarness;
        let mut events = AnthropicEventNormalizer::default();
        let mut turns = CodexTurnNormalizer::new(BridgeConfig::new("T-aisdk", "turn-1"));

        feed(
            &harness,
            &mut events,
            &mut turns,
            json!({"type": "system", "subtype": "init", "session_id": "aisdk-session-1"}),
        );

        // Streaming text deltas arrive as raw stream events.
        feed(
            &harness,
            &mut events,
            &mut turns,
            json!({"type": "stream_event", "event": {"type": "message_start", "message": {"id": "msg_1", "content": []}}}),
        );
        feed(
            &harness,
            &mut events,
            &mut turns,
            json!({"type": "stream_event", "event": {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}}),
        );
        let notifications = feed(
            &harness,
            &mut events,
            &mut turns,
            json!({"type": "stream_event", "event": {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Checking."}}}),
        );
        let methods: Vec<String> = notifications
            .iter()
            .map(|notification| notification_to_jsonrpc(notification).unwrap().method)
            .collect();
        assert_eq!(methods, vec!["item/started", "item/agentMessage/delta"]);

        // The step's final assistant message carries the tool call.
        let notifications = feed(
            &harness,
            &mut events,
            &mut turns,
            json!({
                "type": "assistant",
                "is_partial": false,
                "message": {
                    "id": "msg_1",
                    "stop_reason": "tool_use",
                    "content": [
                        {"type": "text", "text": "Checking."},
                        {"type": "tool_use", "id": "call_1", "name": "Bash", "input": {"command": "ls"}}
                    ]
                }
            }),
        );
        let started_command = notifications
            .iter()
            .find_map(|notification| {
                let rpc = notification_to_jsonrpc(notification).unwrap();
                (rpc.method == "item/started").then(|| rpc.params.unwrap())
            })
            .expect("tool_use should start an item");
        assert_eq!(started_command["item"]["type"], "commandExecution");
        assert_eq!(started_command["item"]["command"], "ls");

        let notifications = feed(
            &harness,
            &mut events,
            &mut turns,
            json!({
                "type": "user",
                "message": {"content": [{"type": "tool_result", "tool_use_id": "call_1", "content": "README.md", "is_error": false}]},
                "tool_use_result": {"stdout": "README.md\n", "stderr": "", "exit_code": 0}
            }),
        );
        let completed = notification_to_jsonrpc(&notifications[0]).unwrap();
        assert_eq!(completed.method, "item/completed");
        let params = completed.params.unwrap();
        assert_eq!(params["item"]["type"], "commandExecution");
        assert_eq!(params["item"]["aggregatedOutput"], "README.md\n");
        assert_eq!(params["item"]["exitCode"], 0);
        assert_eq!(params["threadId"], "aisdk-session-1");

        // Terminal result event ends the turn.
        let event = harness
            .parse_stdout_line(&json!({"type": "result", "subtype": "success"}).to_string())
            .unwrap();
        let normalized = harness.normalize_events(&mut events, event).unwrap();
        assert!(matches!(
            normalized.as_slice(),
            [NormalizedEvent::Result { error: None }]
        ));
    }

    #[test]
    fn command_for_turn_passes_model_and_session_flags() {
        let state = ThreadStateFixture::new("thread-9", Some("claude-sonnet-4-6"));
        let command = AiSdkHarness.command_for_turn(&state.0);
        let args: Vec<String> = command
            .get_args()
            .map(|arg| arg.to_string_lossy().to_string())
            .collect();
        assert_eq!(args, vec!["--model", "claude-sonnet-4-6", "--session-id", "thread-9"]);
    }

    struct ThreadStateFixture(crate::ThreadState);

    impl ThreadStateFixture {
        fn new(id: &str, model: Option<&str>) -> Self {
            Self(crate::ThreadState {
                id: id.to_string(),
                cwd: std::env::temp_dir(),
                model: model.unwrap_or_default().to_string(),
                model_provider: "ai-sdk".to_string(),
                service_tier: None,
                harness_session_id: None,
                completed_turns: Vec::new(),
                process: None,
                thread_started_sent: false,
            })
        }
    }
}
