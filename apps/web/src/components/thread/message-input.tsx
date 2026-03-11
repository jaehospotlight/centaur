"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { ArrowUp, Loader2, Square } from "lucide-react";
import { toast } from "sonner";
import { useHaptics } from "@/components/haptics-provider";
import { useKeyboardHeight } from "@/hooks/use-visual-viewport";
import { Button } from "@/components/ui/button";
import { ChatTextarea } from "@/components/ui/chat-textarea";
import { SurfaceBar } from "@/components/ui/surface-bar";
import { cn } from "@/lib/utils";

type InputMode = "idle" | "running" | "error";

type MessageInputProps = {
  mode: InputMode;
  onSend: (message: string) => Promise<void>;
  onStop?: () => Promise<void>;
  className?: string;
  placeholder?: string;
  hint?: string;
};

const MAX_ROWS = 6;
const LINE_HEIGHT = 22;
const PADDING_Y = 20;
const MAX_HEIGHT = MAX_ROWS * LINE_HEIGHT + PADDING_Y;

const PLACEHOLDERS: Record<InputMode, string> = {
  idle: "Reply with the next instruction…",
  running: "Stop the current run or prepare the next instruction…",
  error: "Retry with clearer direction…",
};

const MODE_LABELS: Record<InputMode, string> = {
  idle: "Ready",
  running: "Running",
  error: "Needs attention",
};

const MODE_HINTS: Record<InputMode, string> = {
  idle: "Enter to send, Shift+Enter for a new line.",
  running: "Enter redirects the run after stopping it first.",
  error: "The last run failed. Your next reply will restart it.",
};

export function MessageInput({
  mode,
  onSend,
  onStop,
  className,
  placeholder,
  hint,
}: MessageInputProps) {
  const [value, setValue] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [isFocused, setIsFocused] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const composingRef = useRef(false);
  const keyboardHeight = useKeyboardHeight();
  const effectiveKeyboardHeight = isFocused ? keyboardHeight : 0;
  const { trigger } = useHaptics();

  const resize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT)}px`;
  }, []);

  useLayoutEffect(resize, [value, resize]);

  const hasText = value.trim().length > 0;
  const showStop = mode === "running" && !!onStop;
  const resolvedPlaceholder = placeholder ?? PLACEHOLDERS[mode];
  const resolvedHint = hint ?? MODE_HINTS[mode];

  async function handleSend() {
    const text = value.trim();
    if (!text || submitting) return;
    setSubmitting(true);
    try {
      await onSend(text);
      setValue("");
      window.requestAnimationFrame(() => trigger("success"));
    } catch {
      window.requestAnimationFrame(() => trigger("error"));
      toast("Unable to send message. Please try again.");
    } finally {
      setSubmitting(false);
      textareaRef.current?.focus();
    }
  }

  async function handleStop() {
    if (!onStop) return;
    trigger("warning");
    setSubmitting(true);
    try {
      await onStop();
    } finally {
      setSubmitting(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (composingRef.current || e.nativeEvent.isComposing) return;

    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      void handleSend();
      return;
    }

    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  }

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    const start = () => { composingRef.current = true; };
    const end = () => { composingRef.current = false; };
    el.addEventListener("compositionstart", start);
    el.addEventListener("compositionend", end);
    return () => {
      el.removeEventListener("compositionstart", start);
      el.removeEventListener("compositionend", end);
    };
  }, []);

  return (
    <SurfaceBar
      className={cn(
        "flex-shrink-0 border-t border-border/70 px-2.5 py-2.5",
        className,
      )}
      style={{
        paddingBottom:
          effectiveKeyboardHeight > 0
            ? `${Math.max(8, effectiveKeyboardHeight)}px`
            : "max(8px, env(safe-area-inset-bottom))",
      }}
    >
      <form
        onSubmit={(e) => { e.preventDefault(); void handleSend(); }}
        className="thread-surface mx-auto flex w-full max-w-content-max items-end gap-3 rounded-[var(--radius-shell)] px-3 py-2.5 transition-[border-color,box-shadow,background-color] duration-fast ease-standard focus-within:border-ring/70 focus-within:bg-card/62 focus-within:ring-2 focus-within:ring-ring/35 md:px-4 md:py-3.5"
        aria-label="Message composer"
      >
        <div className="min-w-0 flex-1">
          <div className="mb-2 flex flex-wrap items-center gap-1.5 md:gap-2">
            <span
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-detail font-medium",
                mode === "error"
                  ? "border-destructive/30 bg-destructive/10 text-destructive"
                  : mode === "running"
                    ? "border-primary/25 bg-primary/10 text-primary"
                    : "border-border/70 bg-background/55 text-muted-foreground",
              )}
            >
              <span
                className={cn(
                  "size-1.5 rounded-full",
                  mode === "error"
                    ? "bg-destructive"
                    : mode === "running"
                      ? "bg-primary"
                      : "bg-muted-foreground/70",
                )}
              />
              {MODE_LABELS[mode]}
            </span>
            <span className="ui-caption">
              {resolvedHint}
            </span>
          </div>

          <label htmlFor="chat-input" className="sr-only">Message</label>
          <ChatTextarea
            ref={textareaRef}
            id="chat-input"
            name="chat-input"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            placeholder={resolvedPlaceholder}
            disabled={submitting}
            rows={1}
            enterKeyHint="send"
            autoComplete="off"
            aria-describedby="chat-input-hint"
            className="min-h-[48px] rounded-[var(--radius-surface)] border-0 bg-transparent px-0 py-0 text-sm leading-6 text-foreground placeholder:text-muted-foreground/75"
          />
          <span id="chat-input-hint" className="sr-only">
            Press Enter to send, Shift+Enter for a new line.
          </span>
        </div>

        {submitting ? (
          <Button type="button" disabled aria-label="Sending message" variant="default" size="icon-lg" className="mb-0.5 flex-shrink-0 rounded-[var(--radius-surface)] bg-primary text-primary-foreground">
            <Loader2 aria-hidden="true" className="size-4 animate-spin" />
          </Button>
        ) : (
          <div className="mb-0.5 flex shrink-0 items-end gap-2">
            {showStop ? (
              <Button
                type="button"
                onClick={() => void handleStop()}
                variant="destructive"
                size="icon-lg"
                className="rounded-[var(--radius-surface)]"
                aria-label="Stop agent"
              >
                <Square aria-hidden="true" className="size-3.5" />
              </Button>
            ) : null}
            <Button
              type="submit"
              disabled={!hasText}
              variant={hasText ? "default" : "ghost"}
              size="icon-lg"
              className={cn(
                "rounded-[var(--radius-surface)] transition-colors duration-base ease-standard",
                hasText
                  ? "bg-primary text-primary-foreground hover:bg-primary/92"
                  : "bg-muted-foreground/15 text-muted-foreground/30 pointer-events-none",
              )}
              aria-label="Send message"
            >
              <ArrowUp aria-hidden="true" className="size-4" />
            </Button>
          </div>
        )}
      </form>
    </SurfaceBar>
  );
}
