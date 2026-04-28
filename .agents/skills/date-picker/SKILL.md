---
name: date-picker
description: "Finds the best date for a Paradigm event by checking holidays, major industry events, and key attendee calendars, then ranking the best options. Use when asked to pick a date, find the best date, compare dates, check date conflicts, or hold a date for an event. Triggers on: date picker, pick a date, best date, check date conflicts, compare dates, hold the date."
---

# Date Picker

Centaur-native port of `paradigm-operations/ai/skills/date-picker`.

Use this skill to recommend the best date for an event by combining:
- holiday conflicts
- major industry event conflicts
- internal Paradigm calendar availability
- external attendee confirmation, when relevant

## Use When

Use this skill when the user asks to:
- find the best date for an event
- compare two or more candidate dates
- check whether a proposed date has conflicts
- see what major conferences or holidays land in a given week or month
- choose the best week for a dinner, summit, offsite, or meeting

Do not use this skill for routine single-person scheduling when the user only needs one person's availability and no broader conflict scan.

## Modes

Choose the lightest-weight mode that answers the request.

- `Full recommendation`: user gave a month, range, or broad window and wants the best option.
- `Quick conflict check`: user gave one specific date and wants to know whether it is clean.
- `Head-to-head comparison`: user gave 2 to 4 specific dates to compare.
- `Conference scan`: user wants to know what major industry events exist in a month, city, or week.

## Inputs To Gather

Ask only for the details that materially affect the answer. Ask in batches of at most 2 or 3 short questions.

Capture these if they are not already known:
- event name
- city and timezone
- date range or explicit candidate dates
- event duration
- key internal attendees
- key external attendees, if any
- day-of-week preferences
- dates already ruled out
- whether co-locating with another major event is desirable or undesirable

If the user gives a very broad range like "sometime this fall," ask them to narrow it to a month or a 4 to 8 week window before doing the full scan.

## Centaur Tooling

Use Centaur-native tools, not legacy shell commands.

### Web research

Use `call websearch search` for holiday and conference checks.

Examples:

```bash
call websearch search '{"query":"2026 Rosh Hashanah dates official","num_results":5,"synthesize":true}'
call websearch search '{"query":"2026 crypto conference calendar","num_results":8,"synthesize":true}'
call websearch search '{"query":"Singapore tech events September 2026","num_results":8,"synthesize":true}'
```

Use `call websearch deep_research` only when the date window is strategically important, the conference landscape is unusually dense, or initial searches are conflicting.

### Calendar checks

Use `call gsuite calendar_events` for internal Paradigm attendees.

Example:

```bash
call gsuite calendar_events '{"calendar_id":"matt@paradigm.xyz","time_min":"2026-09-01T00:00:00-07:00","time_max":"2026-09-30T23:59:59-07:00","max_results":100}'
```

Rules:
- Query the attendee calendar directly by email or known calendar ID.
- Use the narrowest reasonable `time_min` and `time_max` window for the candidate dates.
- If the user gives names rather than emails, infer the email only when it is obvious. If it is ambiguous, ask.
- If a calendar lookup errors or access is missing, say that explicitly and continue the rest of the analysis. Do not invent availability.

If tool contracts are unclear, run `call discover gsuite` or `call discover websearch` once before proceeding.

## Workflow

### 1. Resolve the scheduling problem

Decide which mode applies.

- If the user supplied exact dates, do not regenerate alternatives unless asked.
- If the user supplied a range, generate 5 to 8 candidate start dates.
- Respect the timezone and event duration from the start.

For candidate generation:
- Favor Tuesday through Thursday for dinners and meetings unless the user says otherwise.
- Treat multi-day events as a date window, not a single day.
- Avoid dates that obviously span weekends or holidays unless the user requested that pattern.

### 2. Check holidays

Flag any candidate date that falls on, immediately adjacent to, or meaningfully overlaps major holidays.

Always check these fixed-date or rule-based US holidays:
- New Year's Day
- Martin Luther King Jr. Day
- Presidents' Day
- Memorial Day
- Juneteenth
- Independence Day
- Labor Day
- Columbus Day
- Veterans Day
- Thanksgiving and Black Friday
- Christmas Eve and Christmas Day
- New Year's Eve

Also check floating holidays that commonly create travel or attendance conflicts:
- Rosh Hashanah
- Yom Kippur
- Passover
- Sukkot
- Easter and Good Friday
- Chinese New Year
- Diwali

Use web search to confirm the exact dates for the target year. Prefer official or high-confidence sources over generic SEO calendar pages.

Classify the result as:
- `blocking`: on the holiday or obviously unusable
- `nearby`: within a day or otherwise likely to create travel or family conflict
- `clear`: no meaningful holiday issue found

### 3. Check major industry events

Search for major crypto and tech conferences that overlap the candidate dates.

Start with a broad calendar query, then narrow by city and month when needed.

Recommended searches:

```bash
call websearch search '{"query":"2026 crypto conference calendar","num_results":8,"synthesize":true}'
call websearch search '{"query":"<city> tech events <month> <year>","num_results":8,"synthesize":true}'
call websearch search '{"query":"Consensus Token2049 Devcon Permissionless Breakpoint ETHDenver <year> dates","num_results":8,"synthesize":true}'
```

Always check for these named events when relevant to the year:
- Consensus
- Token2049 Singapore
- Token2049 Dubai
- ETHDenver
- ETH CC
- Devcon
- Devconnect
- Permissionless
- Breakpoint
- Paris Blockchain Week
- Bitcoin Conference
- Korea Blockchain Week
- DAS
- Web Summit
- CES
- TechCrunch Disrupt
- SALT
- Milken

For each conflict, note whether it is:
- `blocking`: a key-attendee magnet or direct overlap
- `advisory`: same week, nearby travel, or relevant but not clearly disqualifying
- `beneficial`: intentional co-location opportunity because the user wants to piggyback on the event

If the user explicitly wants to host around a major conference, treat relevant overlap as a positive signal instead of a penalty.

### 4. Check internal Paradigm calendars

For each key internal attendee:
- query `gsuite.calendar_events` for the candidate window
- inspect any events that overlap the proposed date and time window
- classify the attendee's status per candidate date

Classification:
- `hard conflict`: PTO, travel, all-day event, board meeting, offsite, or another event that is clearly immovable
- `soft conflict`: internal meeting or other conflict that might be movable
- `clear`: no overlapping conflict found
- `unknown`: calendar could not be checked reliably

Calendar guidance:
- Use the event timezone when known; otherwise use the event city timezone.
- For full-day or evening events, check the whole local day, not just a single hour.
- For multi-day events, check every day in the proposed span.
- If one attendee is mission-critical, say so in the recommendation rather than averaging them into the background.

### 5. Handle external attendees

Do not claim external attendee availability unless it has actually been confirmed.

If external attendees matter:
- narrow the field to the dates that survive the holiday, event, and internal-calendar screen
- show the best remaining options to the user
- ask them to confirm external availability for those dates

Once external confirmations arrive:
- mark a key external attendee as `blocking` if they are unavailable
- mark them as `pending` if not yet confirmed
- use confirmed external availability as a tiebreaker or disqualifier in the final ranking

### 6. Score and rank the dates

Use this default rubric unless the user's priorities clearly suggest a different one.

| Factor | Weight | Notes |
|--------|--------|-------|
| Holiday conflicts | 30% | 0 = blocking holiday, 50 = adjacent, 100 = clear |
| Industry event conflicts | 25% | 0 = blocking overlap, 50 = same week or advisory, 100 = clear |
| Internal calendar availability | 30% | percentage of key internal attendees who are clear, adjusted down for hard conflicts |
| Day-of-week fit | 15% | 100 = preferred day, 50 = acceptable, 0 = excluded |

Adjustments:
- If co-location is explicitly desirable, replace the normal conference penalty with a positive note and score accordingly.
- If a key external attendee is confirmed unavailable, remove that date from contention unless the user says otherwise.
- If too much availability is `unknown`, lower confidence and say so explicitly.

### 7. Return the answer

Lead with the recommendation, then show the evidence.

Always include:
1. the top recommendation with 1 to 3 concrete reasons
2. a ranked table of candidate dates
3. a short conflict summary for each option
4. the next step, such as confirming with external attendees or placing a hold

Use a compact markdown table when there are multiple options:

```text
Date recommendations for [event]

| Rank | Date | Day | Score | Holidays | Events | Calendars | Notes |
|------|------|-----|-------|----------|--------|-----------|-------|
| 1 | Sep 15, 2026 | Tue | 92 | Clear | Clear | 5/5 clear | Recommended |
| 2 | Sep 17, 2026 | Thu | 84 | Clear | Near Token2049 | 4/5 clear | One soft conflict |
| 3 | Sep 22, 2026 | Tue | 61 | Near Rosh Hashanah | Clear | 3/5 clear | Two key conflicts |
```

When the user asked for a quick check on a single date, skip the full table and answer with:
- overall verdict
- holiday status
- conference status
- internal availability summary
- whether it is safe to hold pending external confirmation

## Guardrails

- Do not hallucinate holiday dates, conference dates, or calendar availability.
- Do not over-research a one-date question with a full multi-date workflow.
- Do not ask the user to retype information you can infer from their prompt.
- Do not treat missing calendar access as proof that someone is free.
- Be explicit about assumptions, especially timezone assumptions and inferred attendee emails.
- If the user seems to want a conference-adjacent event, ask that directly before penalizing overlap.

## Quick Triggers

- "date picker"
- "pick a date for [event]"
- "find the best date for [event]"
- "check [date] for conflicts"
- "compare [date 1] vs [date 2]"
- "what conferences are in [month]"
