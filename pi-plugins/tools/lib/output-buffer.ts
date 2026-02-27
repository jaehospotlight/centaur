/**
 * Fixed-head + rolling-tail buffer for streaming bash output.
 *
 * Maintains constant memory regardless of output size by keeping the
 * first N lines (head) and last M lines (tail). Used to show beginning
 * + end of long command outputs rather than only the tail.
 */

const DEFAULT_HEAD = 50;
const DEFAULT_TAIL = 50;

/**
 * Truncate an array to head + tail with a message for the gap.
 * Simpler than OutputBuffer — for when you have all items upfront.
 */
export function formatHeadTail<T>(
  items: T[],
  maxItems: number = 100,
  truncatedMsg?: string,
): T[] {
  if (items.length <= maxItems) return [...items];

  const half = Math.floor(maxItems / 2);
  const head = items.slice(0, half);
  const tail = items.slice(-half);
  const skipped = items.length - head.length - tail.length;

  const marker = (truncatedMsg ?? `... [${skipped} lines truncated] ...`) as unknown as T;
  return [...head, marker, ...tail];
}

/**
 * Character-level head+tail truncation for raw strings.
 */
export function headTailChars(text: string, maxChars: number = 64_000): string {
  if (text.length <= maxChars) return text;

  const half = Math.floor(maxChars / 2);
  const head = text.slice(0, half);
  const tail = text.slice(-half);
  const skipped = text.length - maxChars;

  return `${head}\n\n... [${skipped} characters truncated] ...\n\n${tail}`;
}

export class OutputBuffer {
  private head: string[] = [];
  private tail: string[] = [];
  private headFull = false;
  private pendingLine = "";
  totalLines = 0;

  constructor(
    private maxHead: number = DEFAULT_HEAD,
    private maxTail: number = DEFAULT_TAIL,
  ) {}

  /**
   * Add a chunk of output. Handles partial lines across chunk boundaries
   * by buffering the incomplete trailing fragment.
   */
  add(chunk: string): void {
    const text = this.pendingLine + chunk;
    const lines = text.split("\n");

    // Last element is either empty (chunk ended with \n) or a partial line
    this.pendingLine = lines.pop() ?? "";

    for (const line of lines) {
      this.totalLines++;
      this.pushLine(line);
    }
  }

  private pushLine(line: string): void {
    // Fill head buffer first
    if (!this.headFull && this.head.length < this.maxHead) {
      this.head.push(line);
      if (this.head.length === this.maxHead) this.headFull = true;
    }

    // Always maintain rolling tail
    this.tail.push(line);
    if (this.tail.length > this.maxTail) {
      this.tail.shift();
    }
  }

  /**
   * Finalize and format the buffered output.
   * Small outputs are returned whole; large outputs get head + truncation marker + tail.
   */
  format(): { text: string; truncatedLines: number } {
    // Flush any pending partial line
    if (this.pendingLine) {
      this.totalLines++;
      this.pushLine(this.pendingLine);
      this.pendingLine = "";
    }

    const total = this.totalLines;

    // No truncation needed — output fits within both buffers
    if (total <= this.maxHead + this.maxTail) {
      const merged = this.mergeSmallOutput(total);
      return { text: merged.join("\n"), truncatedLines: 0 };
    }

    // Large output: head + marker + tail
    const truncated = total - this.head.length - this.tail.length;
    const parts = [
      ...this.head,
      "",
      `... [${truncated} lines truncated] ...`,
      "",
      ...this.tail,
    ];

    return { text: parts.join("\n"), truncatedLines: truncated };
  }

  /**
   * Merge head and tail for small outputs where they overlap.
   */
  private mergeSmallOutput(total: number): string[] {
    if (total <= this.maxHead) return this.head;
    if (total <= this.maxTail) return this.tail;

    // Find where tail starts relative to head
    const overlapStart = this.head.indexOf(this.tail[0]);
    if (overlapStart === -1) return [...this.head, ...this.tail];

    return [...this.head.slice(0, overlapStart), ...this.tail];
  }
}
