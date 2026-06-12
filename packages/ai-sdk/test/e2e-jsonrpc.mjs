// Offline end-to-end check of the full pipeline:
//   JSON-RPC client -> harness-server ai-sdk --mode jsonrpc -> bridge (mock model)
//
// Usage: node test/e2e-jsonrpc.mjs <path-to-harness-server-binary>
// Exits 0 and prints the notification methods when the turn round-trips.
import { spawn } from "node:child_process";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";

const serverBin = process.argv[2];
if (!serverBin) {
  console.error("usage: node test/e2e-jsonrpc.mjs <harness-server-binary>");
  process.exit(2);
}
const bridgePath = fileURLToPath(new URL("../src/bridge.ts", import.meta.url));

const child = spawn(serverBin, ["ai-sdk", "--mode", "jsonrpc"], {
  env: {
    ...process.env,
    CENTAUR_AISDK_BRIDGE_COMMAND: `node ${bridgePath} --session-id e2e-session --model mock`,
  },
  stdio: ["pipe", "pipe", "inherit"],
});

const send = (value) => child.stdin.write(`${JSON.stringify(value)}\n`);
const methods = [];
let threadId = null;

const timeout = setTimeout(() => {
  console.error("e2e timed out; methods so far:", methods);
  child.kill();
  process.exit(1);
}, 30_000);

createInterface({ input: child.stdout }).on("line", (line) => {
  if (!line.trim()) return;
  const message = JSON.parse(line);

  if (message.id === 1) {
    send({ id: 2, method: "thread/start", params: {} });
  } else if (message.id === 2) {
    threadId = message.result.thread.id;
    send({
      id: 3,
      method: "turn/start",
      params: { threadId, input: [{ type: "text", text: "run the tool" }] },
    });
  } else if (message.method) {
    methods.push(message.method);
    if (message.method === "item/completed") {
      const item = message.params.item;
      console.log(
        `item/completed: ${item.type}` +
          (item.type === "commandExecution"
            ? ` command=${JSON.stringify(item.command)} output=${JSON.stringify(item.aggregatedOutput)} exit=${item.exitCode}`
            : item.type === "agentMessage"
              ? ` text=${JSON.stringify(item.text)} phase=${item.phase}`
              : ""),
      );
    }
    if (message.method === "turn/completed") {
      clearTimeout(timeout);
      const turn = message.params.turn;
      console.log(`turn/completed: status=${turn.status} items=${turn.items.length}`);
      console.log("methods:", methods.join(" "));
      const ok =
        turn.status === "completed" &&
        methods.includes("item/agentMessage/delta") &&
        turn.items.some((item) => item.type === "commandExecution" && item.exitCode === 0) &&
        turn.items.some((item) => item.type === "agentMessage" && item.phase === "final_answer");
      child.kill();
      process.exit(ok ? 0 : 1);
    }
  }
});

send({
  id: 1,
  method: "initialize",
  params: { clientInfo: { name: "e2e" }, capabilities: null },
});
