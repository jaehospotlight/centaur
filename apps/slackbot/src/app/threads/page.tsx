/** @jsxImportSource react */
"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";

const BASE = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

type Thread = {
  slack_thread_key: string;
  container_id: string;
  harness: string;
  agent_thread_id: string | null;
  state: string;
  created_at: number;
  last_activity: number;
  turn_count: number;
  last_result: string;
};

const HARNESS_COLORS: Record<string, { bg: string; fg: string }> = {
  amp: { bg: "rgba(0, 217, 255, 0.12)", fg: "#00d9ff" },
  "claude-code": { bg: "rgba(192, 132, 252, 0.12)", fg: "#c084fc" },
  codex: { bg: "rgba(52, 211, 153, 0.12)", fg: "#34d399" },
};

const STATE_COLORS: Record<string, string> = {
  running: "#22c55e",
  idle: "#52525b",
  working: "#f59e0b",
};

const MONO = '"JetBrains Mono", "SF Mono", "Fira Code", monospace';

function timeAgo(ts: number): string {
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function formatDate(ts: number): string {
  return new Date(ts * 1000).toLocaleDateString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function ThreadsPage() {
  const [threads, setThreads] = useState<Thread[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchThreads = useCallback(async () => {
    try {
      const res = await fetch(`${BASE}/api/threads`);
      const data = await res.json();
      setThreads(data.threads || []);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchThreads();
    const interval = setInterval(fetchThreads, 5000);
    return () => clearInterval(interval);
  }, [fetchThreads]);

  return (
    <main style={styles.main}>
      <div style={styles.header}>
        <div>
          <h1 style={styles.title}>Threads</h1>
          <p style={styles.subtitle}>
            {threads.length} thread{threads.length !== 1 ? "s" : ""}
          </p>
        </div>
        <button onClick={fetchThreads} className="refresh-btn" style={styles.refreshBtn}>
          ↻ Refresh
        </button>
      </div>

      {loading ? (
        <p style={styles.loading}>Loading…</p>
      ) : threads.length === 0 ? (
        <div style={styles.empty}>
          <div style={styles.emptyIcon}>⊘</div>
          <p style={styles.emptyText}>No agent threads</p>
          <p style={styles.emptyHint}>
            Mention @tempo-ai in a Slack thread to start one
          </p>
        </div>
      ) : (
        <div style={styles.tableWrap}>
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={{ ...styles.th, width: "40%" }}>Thread</th>
                <th style={{ ...styles.th, width: "10%" }}>Harness</th>
                <th style={{ ...styles.th, width: "10%", textAlign: "center" }}>State</th>
                <th style={{ ...styles.th, width: "8%", textAlign: "right" }}>Turns</th>
                <th style={{ ...styles.th, width: "14%" }}>Created</th>
                <th style={{ ...styles.th, width: "10%", textAlign: "right" }}>Activity</th>
              </tr>
            </thead>
            <tbody>
              {threads.map((t) => {
                const hc = HARNESS_COLORS[t.harness] || { bg: "#27272a", fg: "#a1a1aa" };
                return (
                  <tr key={t.slack_thread_key} className="thread-card" style={styles.row}>
                    <td style={styles.td}>
                      <Link
                        href={`/threads/${encodeURIComponent(t.slack_thread_key)}`}
                        style={styles.threadLink}
                      >
                        <span style={styles.threadKey}>{t.slack_thread_key}</span>
                        {t.last_result && (
                          <span style={styles.lastResult}>
                            {t.last_result.slice(0, 100)}
                            {t.last_result.length > 100 ? "…" : ""}
                          </span>
                        )}
                      </Link>
                    </td>
                    <td style={styles.td}>
                      <span
                        style={{
                          ...styles.harnessBadge,
                          backgroundColor: hc.bg,
                          color: hc.fg,
                        }}
                      >
                        {t.harness}
                      </span>
                    </td>
                    <td style={{ ...styles.td, textAlign: "center" }}>
                      <div style={styles.stateGroup}>
                        <span
                          className={t.state === "working" ? "state-dot-working" : ""}
                          style={{
                            ...styles.stateDot,
                            backgroundColor: STATE_COLORS[t.state] || "#52525b",
                          }}
                        />
                        <span style={styles.stateLabel}>{t.state}</span>
                      </div>
                    </td>
                    <td style={{ ...styles.td, textAlign: "right", fontFamily: MONO, fontSize: "0.8125rem", color: "#71717a" }}>
                      {t.turn_count}
                    </td>
                    <td style={{ ...styles.td, color: "#52525b", fontSize: "0.8125rem" }}>
                      {formatDate(t.created_at)}
                    </td>
                    <td style={{ ...styles.td, textAlign: "right", color: "#52525b", fontSize: "0.8125rem" }}>
                      {timeAgo(t.last_activity)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}

const styles: Record<string, React.CSSProperties> = {
  main: {
    minHeight: "100vh",
    backgroundColor: "#09090b",
    color: "#e4e4e7",
    fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    padding: "2rem",
    maxWidth: "1200px",
    margin: "0 auto",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    marginBottom: "1.5rem",
    paddingBottom: "1.25rem",
    borderBottom: "1px solid #1c1c1e",
  },
  title: {
    fontSize: "1.375rem",
    fontWeight: 600,
    color: "#fafafa",
    margin: 0,
    letterSpacing: "-0.02em",
  },
  subtitle: {
    fontSize: "0.8125rem",
    color: "#52525b",
    margin: "0.25rem 0 0",
  },
  refreshBtn: {
    background: "none",
    border: "1px solid #27272a",
    borderRadius: "6px",
    color: "#71717a",
    padding: "6px 14px",
    cursor: "pointer",
    fontSize: "0.8125rem",
    fontFamily: "inherit",
    fontWeight: 500,
    transition: "all 0.15s",
  },
  loading: {
    color: "#52525b",
    textAlign: "center",
    padding: "4rem 0",
    fontSize: "0.875rem",
  },
  empty: {
    textAlign: "center",
    padding: "5rem 0",
  },
  emptyIcon: {
    fontSize: "2rem",
    color: "#27272a",
    marginBottom: "1rem",
  },
  emptyText: {
    color: "#52525b",
    fontSize: "1rem",
    marginBottom: "0.375rem",
    fontWeight: 500,
  },
  emptyHint: {
    color: "#3f3f46",
    fontSize: "0.8125rem",
  },
  tableWrap: {
    overflowX: "auto",
    borderRadius: "10px",
    border: "1px solid #1c1c1e",
  },
  table: {
    width: "100%",
    borderCollapse: "collapse",
    tableLayout: "fixed" as const,
  },
  th: {
    textAlign: "left" as const,
    padding: "0.625rem 1rem",
    fontSize: "0.6875rem",
    fontWeight: 600,
    textTransform: "uppercase" as const,
    letterSpacing: "0.05em",
    color: "#3f3f46",
    borderBottom: "1px solid #1c1c1e",
    backgroundColor: "#0c0c0e",
    whiteSpace: "nowrap" as const,
  },
  row: {
    borderBottom: "1px solid #111113",
    transition: "background-color 0.1s",
    cursor: "pointer",
  },
  td: {
    padding: "0.75rem 1rem",
    verticalAlign: "middle" as const,
  },
  threadLink: {
    display: "flex",
    flexDirection: "column" as const,
    gap: "0.25rem",
    textDecoration: "none",
    color: "inherit",
  },
  threadKey: {
    fontSize: "0.8125rem",
    color: "#d4d4d8",
    fontFamily: '"JetBrains Mono", "SF Mono", "Fira Code", monospace',
    fontWeight: 500,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap" as const,
  },
  lastResult: {
    fontSize: "0.75rem",
    color: "#3f3f46",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap" as const,
    lineHeight: 1.4,
  },
  harnessBadge: {
    fontSize: "0.625rem",
    fontWeight: 600,
    textTransform: "uppercase" as const,
    letterSpacing: "0.04em",
    padding: "3px 8px",
    borderRadius: "4px",
    whiteSpace: "nowrap" as const,
  },
  stateGroup: {
    display: "inline-flex",
    alignItems: "center",
    gap: "0.375rem",
    justifyContent: "center",
  },
  stateDot: {
    width: "7px",
    height: "7px",
    borderRadius: "50%",
    flexShrink: 0,
  },
  stateLabel: {
    fontSize: "0.75rem",
    color: "#52525b",
    fontWeight: 500,
  },
};
