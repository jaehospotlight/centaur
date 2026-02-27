import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

export default function (pi: ExtensionAPI) {
  const raw = process.env.PI_INCLUDE_TOOLS;
  if (!raw) return;
  const allowed = raw
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean);
  if (allowed.length === 0) return;

  const applyFilter = () => pi.setActiveTools(allowed);
  pi.on("session_start", async () => {
    applyFilter();
  });
  pi.on("before_agent_start", async () => {
    applyFilter();
  });
}
