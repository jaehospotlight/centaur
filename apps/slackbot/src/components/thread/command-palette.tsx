"use client";

import type { ComponentType } from "react";
import { Command } from "cmdk";
import { ExternalLink, Keyboard, Link2, RefreshCw, Search, Square } from "lucide-react";
import {
  CommandSurfaceIcon,
  CompactDensityIcon,
  ThreadContextIcon,
} from "@/components/thread/icons/thread-icons";
import { threadName } from "@/lib/thread-name";
import type { ThreadSummary } from "@/lib/types";
import { cn } from "@/lib/utils";

type CommandPaletteProps = {
  open: boolean;
  onOpenChange: (nextOpen: boolean) => void;
  threads: ThreadSummary[];
  currentThreadKey: string;
  compactMode: boolean;
  canInterrupt: boolean;
  isRefreshing: boolean;
  onNavigate: (threadKey: string) => void;
  onRefresh: () => void;
  onStop: () => void;
  onCopyUrl: () => void;
  onToggleCompact: () => void;
  onOpenSlack: (() => void) | null;
  onOpenShortcuts: () => void;
};

type PaletteAction = {
  id: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
  shortcut?: string;
  disabled?: boolean;
  keywords?: string;
  run: () => void;
};

function harnessAbbrev(harness: ThreadSummary["harness"]): string {
  if (harness === "claude-code") return "CC";
  if (harness === "pi-mono") return "PI";
  return harness.toUpperCase();
}

function runAndClose(run: () => void, onOpenChange: (nextOpen: boolean) => void): void {
  onOpenChange(false);
  run();
}

export function CommandPalette({
  open,
  onOpenChange,
  threads,
  currentThreadKey,
  compactMode,
  canInterrupt,
  isRefreshing,
  onNavigate,
  onRefresh,
  onStop,
  onCopyUrl,
  onToggleCompact,
  onOpenSlack,
  onOpenShortcuts,
}: CommandPaletteProps) {
  const navigationItems = threads
    .filter((thread) => thread.slack_thread_key !== currentThreadKey)
    .slice(0, 8);

  const actions: PaletteAction[] = [
    {
      id: "stop",
      label: "Stop agent",
      icon: Square,
      shortcut: "S",
      disabled: !canInterrupt,
      keywords: "interrupt cancel halt",
      run: onStop,
    },
    {
      id: "refresh",
      label: isRefreshing ? "Refreshing thread..." : "Refresh thread",
      icon: RefreshCw,
      shortcut: "R",
      disabled: isRefreshing,
      keywords: "reload sync",
      run: onRefresh,
    },
    {
      id: "copy-url",
      label: "Copy thread URL",
      icon: Link2,
      keywords: "copy link share",
      run: onCopyUrl,
    },
    {
      id: "toggle-compact",
      label: compactMode ? "Disable compact mode" : "Toggle compact mode",
      icon: CompactDensityIcon,
      shortcut: "Cmd+.",
      keywords: "density compact collapse",
      run: onToggleCompact,
    },
    {
      id: "shortcuts",
      label: "Show keyboard shortcuts",
      icon: Keyboard,
      shortcut: "Shift+?",
      keywords: "help hotkeys",
      run: onOpenShortcuts,
    },
  ];

  if (onOpenSlack) {
    actions.push({
      id: "open-slack",
      label: "Open in Slack",
      icon: ExternalLink,
      keywords: "slack thread",
      run: onOpenSlack,
    });
  }

  return (
    <Command.Dialog
      open={open}
      onOpenChange={onOpenChange}
      label="Command palette"
      overlayClassName="fixed inset-0 z-40 bg-black/50 backdrop-blur-[1px]"
      className={cn(
        "fixed left-1/2 top-[20vh] z-50 w-[min(92vw,560px)] -translate-x-1/2 overflow-hidden rounded-md border border-border bg-card text-foreground shadow-2xl outline-none",
      )}
    >
      <div className="flex items-center gap-2 border-b border-border px-3 py-2">
        <Search className="size-3.5 text-muted-foreground" />
        <Command.Input
          autoFocus
          placeholder="Type a command or search..."
          className="w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
        />
      </div>
      <Command.List className="max-h-[320px] overflow-y-auto p-1.5">
        <Command.Empty className="px-2 py-4 text-center text-sm text-muted-foreground">
          No results.
        </Command.Empty>

        <Command.Group heading="Navigation" className="text-[11px] text-muted-foreground">
          {navigationItems.map((thread) => {
            const name = thread.thread_name || threadName(thread.slack_thread_key);
            return (
              <Command.Item
                key={thread.slack_thread_key}
                value={`thread ${name} ${thread.slack_thread_key}`}
                keywords={[thread.harness, thread.state, String(thread.turn_count)]}
                onSelect={() => runAndClose(() => onNavigate(thread.slack_thread_key), onOpenChange)}
                className="group flex cursor-pointer items-center gap-2 rounded-sm px-2 py-2 text-sm text-foreground data-[selected=true]:bg-accent"
              >
                <ThreadContextIcon className="size-3.5 shrink-0 text-muted-foreground" />
                <span className="truncate">{name}</span>
                <span className="ml-auto inline-flex items-center gap-1 text-[10px] text-muted-foreground">
                  <span>{harnessAbbrev(thread.harness)}</span>
                  <span>{thread.turn_count}t</span>
                </span>
              </Command.Item>
            );
          })}
        </Command.Group>

        <Command.Separator className="my-1 h-px bg-border" />

        <Command.Group heading="Actions" className="text-[11px] text-muted-foreground">
          {actions.map((action) => (
            <Command.Item
              key={action.id}
              value={action.label}
              keywords={action.keywords?.split(/\s+/)}
              disabled={action.disabled}
              onSelect={() => runAndClose(action.run, onOpenChange)}
              className={cn(
                "flex items-center gap-2 rounded-sm px-2 py-2 text-sm text-foreground data-[selected=true]:bg-accent",
                action.disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer",
              )}
            >
              <action.icon className="size-3.5 shrink-0 text-muted-foreground" />
              <span>{action.label}</span>
              {action.shortcut ? (
                <span className="ml-auto rounded border border-border px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
                  {action.shortcut}
                </span>
              ) : null}
            </Command.Item>
          ))}
        </Command.Group>
      </Command.List>
      <div className="border-t border-border px-3 py-1.5 text-[10px] text-muted-foreground">
        <CommandSurfaceIcon className="mr-1 inline size-3 align-[-1px]" />
        <span className="font-mono">Enter</span> to run • <span className="font-mono">Esc</span> to close
      </div>
    </Command.Dialog>
  );
}
