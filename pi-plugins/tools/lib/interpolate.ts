/**
 * Template variable interpolation for sub-agent system prompts.
 *
 * Resolves placeholders like {cwd}, {roots}, {date}, {os}, {repo}
 * in prompt templates. Lines whose variables resolve to empty are
 * dropped entirely rather than leaving blank labels.
 */

import { execSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

/** Walk up from dir looking for .git to find the workspace root. */
export function findGitRoot(dir: string): string {
  let current = path.resolve(dir);
  while (true) {
    try {
      const stat = fs.statSync(path.join(current, ".git"));
      if (stat.isDirectory() || stat.isFile()) return current;
    } catch {
      // Not found, keep walking
    }
    const parent = path.dirname(current);
    if (parent === current) return dir; // Hit filesystem root
    current = parent;
  }
}

/** Try to get the git remote origin URL for a directory. */
export function getGitRemoteUrl(dir: string): string {
  try {
    return execSync("git remote get-url origin", {
      cwd: dir,
      stdio: ["ignore", "pipe", "ignore"],
    })
      .toString()
      .trim();
  } catch {
    return "";
  }
}

/** Extra context from the parent pi session. */
export interface InterpolateContext {
  sessionId?: string;
  repo?: string;
  /** Agent identity name (default: "Amp") */
  identity?: string;
  /** Harness name, e.g. "pi" or "amp" (default: "pi") */
  harness?: string;
  /** Pre-loaded harness docs section; skips file read if provided */
  harnessDocsSection?: string;
}

/**
 * Resolve template variables in agent prompts.
 *
 * Supported variables: {cwd}, {roots}, {date}, {os}, {repo},
 * {sessionId}, {ls}, {identity}, {harness}, {harness_docs_section}
 *
 * Lines containing a variable that resolves to empty are removed entirely.
 */
export function interpolatePromptVars(
  prompt: string,
  cwd: string,
  extra?: InterpolateContext,
): string {
  const roots = findGitRoot(cwd);
  const date = new Date().toLocaleDateString("en-US", {
    weekday: "short",
    year: "numeric",
    month: "short",
    day: "numeric",
  });
  const repo = extra?.repo ?? getGitRemoteUrl(roots);
  const sessionId = extra?.sessionId ?? "";

  // Build directory listing for {ls}
  let ls = "";
  try {
    ls = fs
      .readdirSync(roots)
      .map((entry) => {
        const full = path.join(roots, entry);
        try {
          return fs.statSync(full).isDirectory() ? `${full}/` : full;
        } catch {
          return full;
        }
      })
      .join("\n");
  } catch {
    /* graceful */
  }

  const vars: Record<string, string> = {
    cwd,
    roots,
    wsroot: roots,
    workingDir: cwd,
    date,
    os: `${os.platform()} (${os.release()}) on ${os.arch()}`,
    repo,
    sessionId,
    ls,
    identity: extra?.identity || "Amp",
    harness: extra?.harness || "pi",
    harness_docs_section: extra?.harnessDocsSection || "",
  };

  const emptyKeys = Object.keys(vars).filter((k) => !vars[k]);
  const filledEntries = Object.entries(vars).filter(([, v]) => !!v);
  const filled = Object.fromEntries(filledEntries);

  let result = prompt;

  // Pass 1: drop entire lines whose variable resolved to empty
  if (emptyKeys.length > 0) {
    const emptyPattern = new RegExp(
      `^.*\\{(${emptyKeys.join("|")})\\}.*\\n?`,
      "gm",
    );
    result = result.replace(emptyPattern, "");
  }

  // Pass 2: substitute all non-empty variables
  const filledKeys = Object.keys(filled);
  if (filledKeys.length > 0) {
    const fillPattern = new RegExp(`\\{(${filledKeys.join("|")})\\}`, "g");
    result = result.replace(fillPattern, (_, key) => filled[key]);
  }

  return result;
}
