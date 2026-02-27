/**
 * Per-path async mutex for file operations.
 *
 * Serializes concurrent edits to the same file path so partial writes
 * and race conditions don't occur. Keyed by resolved absolute path —
 * two relative paths pointing to the same file share one lock.
 */

import * as path from "node:path";

const locks = new Map<string, Promise<void>>();

/**
 * Execute `fn` while holding an exclusive lock on `filePath`.
 * Concurrent calls for the same resolved path queue sequentially.
 */
export async function withFileLock<T>(filePath: string, fn: () => Promise<T>): Promise<T> {
  const key = path.resolve(filePath);

  // Wait for any existing lock on this path to release
  while (locks.has(key)) {
    await locks.get(key);
  }

  let resolve!: () => void;
  const promise = new Promise<void>((r) => {
    resolve = r;
  });
  locks.set(key, promise);

  try {
    return await fn();
  } finally {
    locks.delete(key);
    resolve();
  }
}
