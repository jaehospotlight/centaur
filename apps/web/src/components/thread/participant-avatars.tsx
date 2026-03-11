"use client";

import { useState } from "react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { Participant } from "@/lib/types";
import { cn } from "@/lib/utils";

const FALLBACK_COLORS = [
  "bg-primary/20 text-primary",
  "bg-secondary text-foreground",
  "bg-muted text-foreground",
  "bg-accent text-foreground",
  "bg-primary/12 text-primary",
] as const;
const SLACK_USER_ID_RE = /^U[A-Z0-9]+$/;

function initials(name: string): string {
  const normalized = name.trim().replace(/^@/, "");
  const parts = normalized.split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
}

function colorForId(id: string): string {
  let hash = 0;
  for (let i = 0; i < id.length; i += 1) {
    hash = (hash << 5) - hash + id.charCodeAt(i);
    hash |= 0;
  }
  return FALLBACK_COLORS[Math.abs(hash) % FALLBACK_COLORS.length];
}

function participantLabel(participant: Participant): string {
  const username = String(participant.username || "").trim();
  if (username) return `@${username}`;
  const name = String(participant.name || "").trim();
  if (name && !SLACK_USER_ID_RE.test(name)) return name;
  const id = String(participant.id || "").trim();
  if (!id) return "Participant";
  if (SLACK_USER_ID_RE.test(id)) return `User ${id.slice(-4)}`;
  return id;
}

export function ParticipantAvatar({
  participant,
  label,
  size = 20,
  className,
}: {
  participant?: Participant | null;
  label: string;
  size?: number;
  className?: string;
}) {
  const [imageFailed, setImageFailed] = useState(false);
  const avatarUrl =
    !imageFailed && typeof participant?.avatar_url === "string" && participant.avatar_url.trim().length > 0
      ? participant.avatar_url.trim()
      : null;

  return (
    <span
      className={cn(
        "ring-2 ring-background rounded-full shrink-0 overflow-hidden flex items-center justify-center text-xs font-semibold",
        !avatarUrl && colorForId(participant?.id || label),
        className,
      )}
      style={{ width: size, height: size }}
    >
      {avatarUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={avatarUrl}
          alt=""
          loading="lazy"
          className="h-full w-full object-cover"
          onError={() => setImageFailed(true)}
        />
      ) : (
        initials(label)
      )}
    </span>
  );
}

export function ParticipantAvatars({
  participants,
  max = 3,
  size = 20,
  decorative = true,
}: {
  participants?: Participant[];
  max?: number;
  size?: number;
  decorative?: boolean;
}) {
  const resolved = (participants ?? []).filter((p) => String(p.id || "").trim().length > 0);
  if (resolved.length === 0) return null;
  const visible = resolved.slice(0, max);
  const overflow = resolved.length - visible.length;
  const ariaSummary = resolved.map(participantLabel).join(", ");

  return (
    <div
      className="inline-flex items-center -space-x-1.5"
      aria-hidden={decorative || undefined}
      aria-label={decorative ? undefined : `Participants: ${ariaSummary}`}
    >
      {visible.map((participant) => {
        const label = participantLabel(participant);
        return (
          <Tooltip key={participant.id}>
            <TooltipTrigger asChild>
              <ParticipantAvatar participant={participant} label={label} size={size} />
            </TooltipTrigger>
            <TooltipContent>{label}</TooltipContent>
          </Tooltip>
        );
      })}
      {overflow > 0 && (
        <Tooltip>
          <TooltipTrigger asChild>
            <span
              className="ring-2 ring-background rounded-full bg-secondary text-muted-foreground shrink-0 flex items-center justify-center text-xs font-semibold"
              style={{ width: size, height: size }}
            >
              +{overflow}
            </span>
          </TooltipTrigger>
          <TooltipContent>{overflow} more participant{overflow === 1 ? "" : "s"}</TooltipContent>
        </Tooltip>
      )}
    </div>
  );
}
