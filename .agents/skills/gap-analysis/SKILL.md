---
name: gap-analysis
description: "Reviews batches of Slack-thread user tasks, grades quality across seven dimensions using chain-of-thought reasoning and binary sub-questions, identifies dominant failure modes, and selects focused improvement fixes. Use for nightly self-improvement review passes or any task-quality gap analysis."
---

# Gap Analysis

Run one batch review pass over compact structured evidence packs for Slack-thread user tasks.

## Scope

Use this skill when the input is a batch of reconstructed user tasks and the goal is to:

- grade each task on the required seven dimensions,
- identify below-bar tasks,
- infer the dominant failure modes,
- synthesize a simple v1 backlog,
- select the highest-value fixes.

This skill is judgment-heavy. Do not ask for raw logs or full transcripts if the provided structured evidence is sufficient.

## Evidence Rules

Treat the workflow-provided evidence pack as the source of truth.

Prioritize evidence in this order:

1. Original ask text.
2. Small prior-context window.
3. Follow-up user behavior after delivery.
4. Final delivered output text.
5. Execution summary signals (tool calls, errors, duration).

Follow-up messages are provided as raw text. Interpret them semantically: read the actual words and determine whether the user is satisfied, correcting, re-asking, or expressing frustration. Do not rely on keyword matching or substring heuristics.

Do not assume silence means success. No follow-up is weak positive evidence only.

If the evidence is incomplete, say so in the task confidence instead of inventing missing facts.

## Evaluation Method

For every task, work through these steps in order:

1. **Restate the user's task** in one sentence. This forces comprehension before judgment.
2. **Quote the key evidence** — cite specific text from the ask, delivery, or follow-ups that drives your assessment. Do not make abstract claims without grounding them.
3. **Answer the binary sub-questions** for each dimension (see rubric).
4. **Write a one-sentence reasoning trace** per dimension explaining your score.
5. **Assign the numeric score** (0-4) per dimension.
6. **Compute the composite score** as a weighted average (see below).
7. **Classify as above-bar or below-bar** based on composite threshold.

This chain-of-thought-before-scoring order is mandatory. Do not assign scores first and rationalize after.

## Required Grading Dimensions

Grade every task on exactly these seven dimensions:

1. `completion`
2. `correctness`
3. `research_quality`
4. `verification_quality`
5. `tool_calling_quality`
6. `subagent_usage_quality`
7. `communication_quality`

Use a 0-4 integer scale for each dimension.

See `references/rubric.md` for the full rubric with binary sub-questions and score anchors.

## Composite Score

Compute one weighted composite per task for quick triage:

```
composite = (
    0.25 * completion +
    0.20 * correctness +
    0.15 * research_quality +
    0.15 * verification_quality +
    0.10 * tool_calling_quality +
    0.05 * subagent_usage_quality +
    0.10 * communication_quality
)
```

Normalize to 0-100 by multiplying by 25.

A task is **below-bar** when `composite < 62` (roughly equivalent to mostly-3s with one weak dimension).

## Grading Rules

Interpret user behavior conservatively:

- Explicit correction or re-ask is strong negative evidence for completion and correctness.
- Repeated user steering after delivery is strong negative evidence.
- Positive acknowledgment ("thanks", "looks good") is meaningful but not perfect proof.
- No follow-up is weak positive evidence only — do not assume satisfaction.

Interpret execution signals as supporting evidence:

- Non-terminal or failed execution status should heavily lower completion.
- Zero verification plus code edits should cap verification_quality at 1.
- Repeated tool retries and tool errors should lower tool_calling_quality.
- No subagent use on a clearly multi-domain task can lower subagent_usage_quality.
- These are features, not final verdicts — the reasoning trace must explain how they influenced the score.

## Prioritization Rules

Prioritize user-value failures first.

Rank failure classes in this order:

1. intent misses
2. research misses
3. verification misses
4. tool misuse
5. subagent misuse
6. missing capabilities (recurring pattern suggests a new skill or persona)
7. reliability issues
8. communication misses
9. style or polish

Do not let cosmetic issues outrank meaningful user-facing failures.

## v1 Clustering Rule

Keep backlog synthesis intentionally simple.

Cluster only by:

- dominant failure mode,
- likely fix surface,
- representative thread evidence.

Do not invent a complex clustering engine. If two failures share the same root cause and the same fix surface, they are one backlog item.

## Cross-Run Deduplication

The workflow provides a list of recent fix titles that have already been attempted. This list appears in the prompt as a JSON array under "Recently attempted fix titles."

Before selecting fixes, check whether your proposed fix title substantially overlaps with a recently attempted fix. Use semantic comparison, not exact string matching. If it overlaps, either:

- skip it (the prior fix should address it), or
- explain why the prior fix was insufficient and a new attempt is warranted.

A separate reconciliation step will also deduplicate your fixes against learning-synthesis proposals after this pass. Focus on selecting the best fixes from the evidence you see; the workflow handles cross-pass merging.

## Allowed Fix Types

Use exactly these fix types:

- `bug_fix`
- `workflow_fix`
- `prompt_tweak`
- `tool_improvement`
- `new_skill`
- `new_persona`

Treat `new_skill` and `new_persona` as first-class fix types.

When selecting `new_skill` or `new_persona`, you must include an explicit justification answering:

1. Is this failure caused by the agent not knowing what to do, or not being able to do it?
2. Does the pattern appear in 2+ reviewed tasks?
3. Why is a new capability the right fix instead of a code, workflow, prompt, or tool change?

## Stop Rules

If all tasks score above-bar (composite >= 62) and no dimension scores below 3 in 2+ tasks, report a healthy system and select zero fixes. Do not manufacture improvements when none are warranted.

If all tasks are above-bar but one dimension consistently scores below 3 across 2+ tasks, you may propose one targeted fix for that dimension. Frame it as "system is healthy overall but this specific dimension has room to improve" — not as a failure.

If evidence is too thin to grade confidently (e.g., fewer than 3 tasks with sufficient context), report low-confidence and select zero fixes.

Only select fixes where you can name a specific target file and a concrete change. If you cannot, the diagnosis is too vague to act on — report it in `top_failure_modes` but do not select it as a fix.

## Output Contract

Return JSON only. Use **exactly** these top-level keys — do not rename, omit, or add extra top-level keys:

```json
{
  "tasks_reviewed": 0,
  "below_bar_count": 0,
  "below_bar_rate": 0.0,
  "task_reviews": [],
  "top_failure_modes": [],
  "selected_fixes": []
}
```

### `task_reviews` array — one entry per task

Each entry must include all of these fields:

```json
{
  "task_id": "task-1",
  "thread_key": "C123:1700.100",
  "user_task_restatement": "User asked the bot to ...",
  "key_evidence": "User said '...' and the bot replied '...'",
  "overall": "below_bar",
  "composite_score": 52,
  "confidence": "medium",
  "dominant_failure_mode": "verification_miss",
  "scores": {
    "completion": 2,
    "correctness": 3,
    "research_quality": 2,
    "verification_quality": 1,
    "tool_calling_quality": 3,
    "subagent_usage_quality": 3,
    "communication_quality": 3
  },
  "reasoning": {
    "completion": "One sentence.",
    "correctness": "One sentence.",
    "research_quality": "One sentence.",
    "verification_quality": "One sentence.",
    "tool_calling_quality": "One sentence.",
    "subagent_usage_quality": "One sentence.",
    "communication_quality": "One sentence."
  },
  "followup_interpretation": "What the follow-up behavior tells us about quality."
}
```

### `top_failure_modes` array

```json
{
  "failure_mode": "verification_miss",
  "count": 3,
  "representative_threads": ["C123:1700.100"]
}
```

### `selected_fixes` array — the most important output

Each fix must be **specific and actionable**. It must name the exact target surface (file, prompt, or config) that should change. Vague recommendations like "add better verification" are not acceptable — say exactly what should change and where.

Required fields:

```json
{
  "title": "Add pre-delivery lint check to eng persona PROMPT.md",
  "fix_type": "prompt_tweak",
  "target_surface": "tools/personas/eng/PROMPT.md",
  "what_to_change": "Add a verification reminder: before delivering code changes, run ruff check and confirm the change compiles.",
  "dominant_failure_mode": "verification_miss",
  "priority": "high",
  "why_now": "3 of 8 reviewed tasks lacked verification — highest-frequency pattern.",
  "evidence_quotes": ["User: 'that didn't work'", "No lint step before delivery"],
  "source_threads": [
    {
      "thread_key": "C123:1700.100",
      "channel": "C123",
      "thread_ts": "1700.100"
    }
  ],
  "representative_tasks": ["task-1"],
  "new_capability_justification": ""
}
```

The `target_surface` field must name a real file or component in the Centaur codebase. Valid targets include:

- `services/sandbox/SYSTEM_PROMPT.md` — the base system prompt
- `tools/personas/{name}/PROMPT.md` — a persona overlay
- `.agents/skills/{name}/SKILL.md` — a skill file
- `workflows/{name}.py` — a workflow file
- `tools/{category}/{name}/client.py` — a tool implementation
- `services/api/api/*.py` — API code

If you cannot name a specific target, the fix is too vague. Sharpen it or decline to select it.

## Selection Limits

Respect the workflow-provided maximum selected-fix count.

Select fewer than the maximum if the evidence is weak or all tasks are above-bar.

## Scorecard

When asked for scorecard phrasing, use the template in `references/scorecard.md`.

## Reference Files

- Read `references/rubric.md` for the exact rubric with binary sub-questions and score anchors.
- Read `references/scorecard.md` for the lean nightly scorecard format.
