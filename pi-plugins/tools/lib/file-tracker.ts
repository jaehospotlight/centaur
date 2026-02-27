/** Track file changes for undo support and diff generation. */

import { diffLines, createPatch } from "diff";

export interface FileChange {
  path: string;
  beforeContent: string | null;
  afterContent: string;
  timestamp: number;
  toolCallId: string;
  isNewFile: boolean;
}

const changes: FileChange[] = [];

export function saveChange(change: FileChange): void {
  changes.push(change);
}

export function loadChanges(): FileChange[] {
  return [...changes];
}

export function findLatestChange(
  filePath: string,
  toolCallIds?: string[],
): FileChange | undefined {
  for (let i = changes.length - 1; i >= 0; i--) {
    const c = changes[i];
    if (c.path === filePath) {
      if (toolCallIds && !toolCallIds.includes(c.toolCallId)) continue;
      return c;
    }
  }
  return undefined;
}

export function revertChange(change: FileChange): string | null {
  return change.beforeContent;
}

/**
 * Generate a simple unified diff between two strings.
 */
export function simpleDiff(
  filePath: string,
  oldContent: string,
  newContent: string,
): string {
  const patch = createPatch(filePath, oldContent, newContent, "", "", {
    context: 3,
  });
  return patch;
}
