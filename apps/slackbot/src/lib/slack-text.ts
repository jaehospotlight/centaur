export const MAX_SLACK_TEXT_CHARS = 3800;

export function truncateSlackText(text: string): string {
  const safe = text.trim();
  if (!safe) return "";
  if (safe.length <= MAX_SLACK_TEXT_CHARS) return safe;
  return safe.slice(0, MAX_SLACK_TEXT_CHARS - 18).trimEnd() + "\n\n... (truncated)";
}
