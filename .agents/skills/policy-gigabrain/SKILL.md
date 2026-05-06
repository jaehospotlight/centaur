---
name: policy-gigabrain
description: "Policy team intelligence system for Hill briefings, policy prep notes, staffer tracking, staffer roster batches, bill analysis, vote prediction, and legislative trend detection. Use when asked about congressional meetings, policy/Hill/member/staffer prep notes, staffer rosters, legislation, regulatory actions, rulemakings, whip counts, policy team workflows, or any question about OCC, SEC, CFTC, FDIC, FinCEN, Treasury guidance, stablecoins, GENIUS Act, market structure bills, or crypto regulation. Triggers on: policy question, regulatory impact, bill analysis, legislation impact on portfolio, policy prep notes, Hill prep notes, member prep notes, staffer prep notes, staffer roster, chief of staff roster, legislative director roster, policy Google Doc prep. Do not use for company, LP, portfolio, IR, or general meeting prep; defer those requests to gtm, tldr, LP-meeting-prep, or ir-companyprep."
---

# Policy Gigabrain

Centralized intelligence system for government affairs. Generates meeting briefers, tracks staffers and legislators, monitors legislation, predicts votes, and surfaces portfolio-relevant regulatory actions.

## Routing Guardrails

- Use this skill only when the request is clearly policy-contextual: congressional, Hill, member, staffer, regulator, legislation, rulemaking, agency, or policy-team work.
- Do **not** use this skill for company, LP, portfolio, IR, or general meeting prep. Defer those requests to `gtm`, `tldr`, `LP-meeting-prep`, or `ir-companyprep` as appropriate.
- Generic requests for "prep notes," "Google Doc prep," "not the usual memo," or "facts and substance" are not enough by themselves. They must be paired with congressional, member, staffer, Hill, regulator, legislation, or policy context.

## ⚠️ MANDATORY FIRST STEP: Policy Explainer Index

**Before answering ANY policy or regulatory question — before running web searches or reading external sources — you MUST first check the Paradigm Policy team's internal analysis.**

```bash
call discover gsuite
call gsuite docs_get_text '{"document_id":"1yiKL4NgJfT0cAXehqHvaYC1mMezKdDhxwnr8Gm8aa6c"}'
```

This is the **Policy Explainer Index** ([link](https://docs.google.com/document/d/1yiKL4NgJfT0cAXehqHvaYC1mMezKdDhxwnr8Gm8aa6c/edit?tab=t.0)), maintained by the Policy team. It contains Paradigm's internal analysis and takes on major regulatory developments (GENIUS Act, FDIC rulemakings, SEC actions, etc.).

**Why this matters:** The Policy team's analysis includes Paradigm-specific context, portfolio impact assessments, and strategic framing that external sources cannot provide. External web searches should only supplement — never replace — the team's own work.

**Workflow:**
1. Read the Policy Explainer Index to check if the topic has been analyzed
2. If an explainer exists, read the linked analysis doc for full detail
3. Only then supplement with external sources (OCC/SEC/CFTC websites, Federal Register, etc.) if needed
4. Always cite the internal analysis as the primary source

## Core Capabilities

| Function | Description |
|----------|-------------|
| **Meeting Briefers** | Auto-generate one-pagers for Hill meetings |
| **Staffer Tracking** | Track congressional/regulatory staff careers, relationships, and exact-match roster batches |
| **Bill Tracking** | Monitor legislation with momentum scores and status |
| **Vote Prediction** | Maintain whip sheets with stance, confidence, rationale |
| **Trend Detection** | Surface emerging patterns across jurisdictions |
| **Portfolio Impact** | Flag legislation affecting portfolio companies |

---

## Data Sources

### External APIs

| Source | Tool | Purpose |
|--------|------|---------|
| **Congress.gov** | `call congress` | Bills, members, committees, hearings, votes, amendments |
| **Federal Register** | `call fedreg` | Regulatory dockets, comment periods, rulemakings |
| **OpenFEC** | `call openfec` | Campaign contributions, candidates, committees, filings |
| **LegiStorm** | `call legistorm` | Staffer database, career tracking, office moves |
| **Plural Policy** | — | Bill momentum scores, AI summaries (future) |

### Internal Sources

| Source | Tool | Use For |
|--------|------|---------|
| **Shift / paradigmdb** | `call paradigmdb` | Portfolio companies, prior interactions, notes |
| **Slack** | `call slack search_messages` | Policy team discussions, intel |
| **GSuite** | `call gsuite` | Meeting notes, Hill interaction logs, Drive docs |
| **Archived docs / notes** | `call gsuite`, `call slack search_messages`, `call websearch search` | Archived policy documents, notes, and discussion |

---

## Workflows

### 1. Meeting Briefer Generation

Generate a policy briefing memo before Hill meetings.

**Trigger Phrases** (policy-qualified requests from Madison, Dominique, Alex G., Justin, Stefan, Katie, or Caitlin):
- "Write a policy briefing memo for [member/staffer name, title]"
- "Briefing memo for Senator/Representative/staffer [Name]"
- "Policy briefer for [Name]"
- "Hill meeting brief for [Name]"
- "Policy prep notes for [Name]"
- "Hill prep notes for [Name]"
- "Member prep notes for [Name]"
- "Staffer prep notes for [Name]"
- "Policy Google Doc prep for [Name]"
- "Put the Hill/member/staffer/policy prep in a Google Doc"

**Input:** Member/staffer name, meeting context, date, and any requested topical sections (for example: crypto knowledge, prediction markets, AI, defense tech, robotics)

**Output Mode Selection:**
- Default to **operator brief mode** for standard policy requests like "briefing memo," "policy briefer," "Hill meeting brief," or member/staffer meeting brief.
- Switch to **prep-notes mode** only when the request is already policy-contextual and the user asks for something like "not the usual memo," "facts and substance," "prep notes," or a document handoff, or otherwise signals they want dense member/staffer prep rather than a polished memo.
- If the user specifies sections to include or exclude, follow that list literally. Do not add extra sections for symmetry.
- Create or update a Google Doc only when the user explicitly asks for a document in the current request and the task is clearly policy-contextual. Otherwise, answer in-thread.

**Steps:**
1. Read the Policy Explainer Index first, then check Shift / slack / notes for prior Paradigm context and any portfolio-company relevance that sharpens the read.
   ```bash
   call slack search_messages '{"query":"from:#policy [member_name]"}'
   call paradigmdb notes_search '{"query":"[member_name]"}'
   call paradigmdb notes_search '{"query":"[relevant_topic_or_company]"}'
   ```
2. Verify any company example in Shift before mentioning it. Only use Paradigm portfolio companies.
3. Look up member profile via web search (committee assignments, voting history, public statements, current lane)
4. Find relevant pending legislation:
   ```bash
   call congress bills '{"congress":119}'
   call congress bill '{"congress":119,"type":"s","number":123}'
   ```
5. Check FEC for campaign contribution context when it materially helps:
   ```bash
   call openfec candidates '{"name":"[member_name]"}'
   call openfec contributions '{"contributor_name":"[member_name]"}'
   ```
6. Cross-reference with paradigmdb for portfolio company relevance:
   ```bash
   call paradigmdb db_query '{"query":"SELECT * FROM \"Organization\" WHERE name ILIKE '\''%relevant_company%'\'';"}'
   ```
7. Generate the selected output shape below

**Shared Format Rules:**
- Write these as meeting prep deliverables, not formal research memos.
- Use short paragraphs and crisp bullets. Prefer direct sentences over issue-summary prose.
- Do **not** use the old memo scaffolding (`Executive Summary`, `Background`, `Primary Ask / Secondary Objectives / Success Criteria`, `Specific Topics To Address`) unless a policy-team member explicitly asks for it.
- Include only the topical sections the prompt asks for or that clearly earn their place. Common sections include `Crypto Knowledge`, `Stance on Prediction Markets`, `Stance on AI`, `Stance on Defense Tech`, and `Stance on Robotics`.
- Use less interpretive language. Favor "this is the lane" and "this is what they are likely to care about" over broader ideological framing.
- If you mention a portfolio company, it must be a **Paradigm portfolio company verified in Shift**. Use **one company by default**. Mention it only if it materially sharpens the memo.
- Put the company mention in the **second bullet** of the relevant topical section after first establishing the member read.
- Company mentions should focus on the business and the concrete policy lane it makes real. Use public toplines and high-level internal context when helpful, but do not add a separate company sidebar.

**Operator Brief Mode:**
- Use this when the user asks for the usual policy briefing memo shape.
- Start with the office read, then move into the lanes that matter for the meeting.

**Prep-Notes Mode:**
- Use this when the user wants dense policy prep notes, a less polished Hill/member/staffer memo, or an explicitly requested policy Google Doc handoff.
- Lead with factual bullets, not connective tissue. Do not add framing lines like "Below is a memo," "taken together," "more broadly," or "the key takeaway is."
- Keep each bullet loaded with one concrete read, fact, vote signal, committee lane, or policy implication. If a section needs context, put it in another bullet, not a throat-clearing sentence.
- Prefer section labels like `Office Read`, `Biography`, `Goals`, and only the topical lanes the user asked for. If the user only wants selected sections, omit everything else.
- Omit empty sections rather than filling them with generic scene-setting.
- If a section needs a short paragraph, keep it factual and avoid editorial transitions between paragraphs and bullets.
- When the user explicitly asks for a Google Doc, the final document must use real Google Docs headings and native bulleted-list formatting, not literal `#`, `##`, `-`, or `•` characters left in plain text. The bullet glyphs in the templates below are illustrative only; convert them to native Docs bullets during the formatting pass.

**Prep-Notes Template:**
```
Office Read
• [Direct read on the office and the productive lane]
• [What to avoid or where not to overreach]

Biography
• [Role, committee seat, or prior career fact that changes the read]
• [Any other fact that changes how they process the issue]

Goals
• [Goal 1]
• [Goal 2]

[Optional user-selected topical section]
• [Fact-dense bullet]
• [Optional verified company example in bullet two if it materially sharpens the lane]
• [Fact-dense bullet]
```

**Operator-Brief Template:**
```
Landscape Summary
[2 short paragraphs on why this office matters, what lane is productive, and what frame to avoid.]

Biography
[1-2 short paragraphs on role, committee seats, prior career, and anything that changes how they process the issue.]

Goals
• [Goal 1]
• [Goal 2]
• [Goal 3]

Crypto Knowledge
• [Short, concrete bullet]
• [Optional second bullet with one verified Paradigm company if it materially sharpens the lane]
• [Short, concrete bullet]

Stance on Prediction Markets
• [Short, concrete bullet]
• [Optional company/business example in bullet two if relevant]
• [Short, concrete bullet]

Stance on AI
• [Short, concrete bullet]
• [Optional company/business example in bullet two if relevant]
• [Short, concrete bullet]

Stance on Defense Tech
• [Short, concrete bullet]
• [Optional company/business example in bullet two if relevant]
• [Short, concrete bullet]

Stance on Robotics
• [Short, concrete bullet]
• [Optional company/business example in bullet two if relevant]
• [Short, concrete bullet]
```

**Section Selection Rules:**
- In operator brief mode, `Landscape Summary`, `Biography`, and `Goals` are the default anchor sections.
- In prep-notes mode, default to `Office Read`, `Biography`, and `Goals` unless the user asks for a different subset.
- If the user asks for only one or two sections, provide only those sections plus any minimal orientation needed to make them usable.
- Add topical sections only when the prompt, agenda, or office lane makes them useful.
- Do not force symmetry. A strong memo may have `Crypto Knowledge` and `Stance on Defense Tech` but no AI section, or AI and robotics but no prediction-markets section.
- If a section has nothing useful to say, omit it.

**Google Docs Formatting Checklist:**
1. Only create or update a Google Doc when the user explicitly asks for a document in the current request and the task is clearly policy-contextual.
2. Run `call discover gsuite` before any Docs mutation so you use the live method names.
3. Create or open the Google Doc with `call gsuite docs_create` or `call gsuite docs_get`.
4. Use `call gsuite docs_get` to determine the current document end index, then write content with `call gsuite docs_insert` and format it with `call gsuite docs_batch_update`.
5. Use `call gsuite docs_batch_update` to convert section labels into heading styles and body ranges into native Google Docs bulleted lists. Do not stop at pasted plain text or literal bullet glyphs.
6. Run `call gsuite docs_get` after the formatting pass and verify the structure is real headings plus native bullets, not literal marker characters sitting in body text.
7. If verification fails, fix the document before returning it.

**Company-Reference Example:**
```text
Stance on Defense Tech
• Kennedy should be receptive to defense tech when it is framed around readiness, industrial capacity, and strategic competition, not startup culture.
• True Anomaly is a useful example. It just raised $650 million, is building spacecraft and autonomy software for contested-space missions, and is already tied to Space Force work.
• The strongest pitch is that the U.S. should make room for trusted new defense suppliers that can build strategically important systems at scale without lowering oversight.
```

### 2. Staffer Tracking

Track congressional and regulatory staffers relevant to crypto policy.

#### Staffer Roster Batch

Use this workflow when the user wants a roster across multiple offices, especially for current Chiefs of Staff, Legislative Directors, and finance-coverage staffers.

**Default Matching Rules:**
- Use exact current-title matches for `Chief of Staff` and `Legislative Director` unless the user explicitly asks for a broader role set.
- Use exact LegiStorm issue-tag matches for `Finance and financial sector` when the user asks for finance or financial-services staffers.
- If the user names additional roles or issue tags, follow that list literally.
- Do **not** silently broaden to adjacent titles such as `Deputy Chief of Staff`, `Senior Advisor`, or `Economic Policy Advisor`, and do **not** expand finance coverage to adjacent tags unless the user explicitly asks. Put those names in `Unverified matches` instead of the verified roster.
- If LegiStorm does not expose a current title, email, or issue tag, leave the field as `—` rather than inferring it from older or adjacent evidence.

**Required Provenance Per Entry:**
- Every verified row must include a `Provenance` field naming the source that verified the entry, such as `LegiStorm`, `committee roster`, or `public bio`.
- If the role and issue coverage came from different sources, list both so the handoff stays auditable.
- If you cannot name the verifying source for a row, move it to `Unverified matches` instead of the main roster.

**Workflow:**
1. Run `call discover legistorm` and `call discover gsuite` before any lookup or sheet write so you use the live method names.
2. Normalize the office list and requested role set. For generic roster asks, default to exact `Chief of Staff`, exact `Legislative Director`, and exact `Finance and financial sector` matches.
3. Query each office separately and keep the verified roster limited to exact matches.
4. Return the verified roster first as a compact table with these columns: `Office`, `Staffer`, `Role`, `Issue Tag`, `Email`, `Provenance`, `Notes`.
5. Put broader coverage guesses, stale hits, partial matches, or rows with missing provenance in a separate `Unverified matches` section with the reason each row did not qualify.
6. If the request is a continuation with more offices, preserve the same exact-match rules and extend only the office list unless the user explicitly changes the filters.

**Delivery And Continuation Rules:**
- If a Google Sheet link or spreadsheet ID is already in-thread, append or update the roster there and return the sheet link plus a short in-thread summary.
- If no spreadsheet target is present, return the roster in Slack and explicitly say that the result is staying in Slack because no sheet target was provided.
- Do not imply sheet delivery happened unless you actually wrote to the sheet.

**Routing Examples: should use Staffer Roster Batch**
- "Pull the current Chiefs of Staff, Legislative Directors, and finance staffers for these offices."
- "Build a verified roster across these House offices with exact Chief of Staff and Legislative Director matches plus finance coverage."
- "Continue the staffer roster and add these new Senate offices using the same exact filters."
- "Export the verified Legislative Directors and finance-tagged staffers into this spreadsheet: [sheet link]."
- "Give me a cleaned LegiStorm roster for Chiefs of Staff and Legislative Directors across this office list."

**Routing Examples: paraphrases that should also use Staffer Roster Batch**
- "For the offices below, who are the current chiefs, LDs, and exact finance-coverage aides?"
- "Take the same office batch and extend the verified staff list with only title-exact CoS and LD hits plus finance-tag matches."

**Routing Examples: should not use Staffer Roster Batch**
- "Write prep notes for this Senator meeting."
- "Who on Senate Banking should we know for the upcoming markup?"
- "Summarize this staffer's background and likely priorities."

**Key Roles to Track:**
- Legislative Directors (LD)
- Committee Counsel (especially Banking, Finance, Agriculture)
- Personal Office Chiefs of Staff
- Leadership Staff
- Executive branch personnel rotating to legislative

**Data Points:**
- Current role and office
- Committee assignments
- Policy areas covered
- Career trajectory
- Paradigm touchpoints
- Alma mater (for relationship mapping)

**Flags to Surface:**
- Junior staff moving to senior roles (build relationships early)
- Committee transfers (new jurisdictional exposure)
- Executive → legislative rotations
- Departures from key offices

**Search Commands:**
```bash
# Find prior interactions with staffer
call slack search_messages '{"query":"[staffer_name]"}'
call gsuite gmail_search '{"query":"[staffer_name]"}'

# Check if mentioned in notes
call paradigmdb notes_search '{"query":"[staffer_name]"}'

# LegiStorm lookup
call legistorm staff '{"name":"[staffer_name]"}'
```

### 3. Bill Tracking & Analysis

Monitor crypto-relevant legislation across federal and state jurisdictions.

**Federal Focus:**
- Senate Banking Committee
- House Financial Services Committee
- Agriculture Committees (CFTC jurisdiction)
- Judiciary Committees (DOJ, IP)

**State Priorities:** NY, TX, CA, WY, IL (active crypto agendas)

**Track Per Bill:**
- Bill number and title
- Sponsors and cosponsors
- Committee referral and status
- Hearing schedule
- Markup dates
- Floor action timeline
- Amendment activity
- Paradigm position (support/oppose/monitor)

**Search Commands:**
```bash
# Search bills via Congress.gov API
call congress bills '{"congress":119,"limit":50}'
call congress bill '{"congress":119,"type":"hr","number":4763,"detail":"summaries"}'

# Search hearings
call congress hearings '{"congress":119,"chamber":"senate"}'
call legistorm townhalls '{}'

# Search for internal discussions
call slack search_messages '{"query":"[bill number]"}'
```

### 4. Vote Prediction / Whip Sheet

Maintain running vote counts for priority legislation.

**Whip Sheet Fields:**
| Field | Values |
|-------|--------|
| Stance | Support / Lean Support / Uncommitted / Lean Oppose / Oppose |
| Strength | Firm / Soft |
| Rationale | Why we believe this |
| Key Influencer | Who can move them |
| The Ask | What we need from them |
| Next Action | Follow-up task |
| Owner | Paradigm team member |
| Last Verified | Date of last confirmation |
| Evidence | Meeting notes, public statements |

**Prediction Inputs:**
- Historical voting patterns (VoteSmart, GovTrack)
- Cosponsor networks
- Public statements
- Committee behavior
- Party leadership signals
- Direct intelligence from meetings

**Update Process:**
1. After each Hill interaction, log stance update
2. Flag inconsistencies between public statements and private positions
3. Surface members whose stance has shifted

### 5. Coalition & Opposition Mapping

Track who is lobbying on which bills.

**Entities to Track:**
- Industry groups (Chamber, trade associations)
- Advocacy organizations
- Companies (competitors, allies)
- Think tanks
- Other crypto firms

**Per Entity:**
- Position on key bills
- Lobbying intensity (high/medium/low)
- Key contacts
- Coalition membership

### 6. Trend Detection

Surface emerging patterns before they become consensus.

**Signals to Monitor:**
- Bill introduction clusters (3+ states with similar language)
- Hearing topic frequency
- Floor statement themes
- Regulatory action patterns
- Model legislation from ALEC, ULC

**State AG Actions:**
- Enforcement actions in priority states
- Settlement patterns
- New investigation announcements

**Search Commands:**
```bash
# Search Federal Register for crypto-related regulatory actions
call fedreg search '{"query":"cryptocurrency","agency":"securities-and-exchange-commission"}'
call fedreg search '{"query":"digital assets","agency":"commodity-futures-trading-commission"}'
call fedreg search '{"query":"stablecoin","type":"PRORULE"}'

# State-level via web search
web_search "state cryptocurrency legislation 2026"
```

### 7. Regulatory Docket Monitoring

Track SEC, CFTC, FinCEN, OCC, Treasury rulemakings.

**Per Docket:**
- Agency and docket number
- Proposed rule summary
- Comment deadline
- Paradigm response status (draft/submitted/none)
- Portfolio company impact

**Search Commands:**
```bash
# Open comment periods
call fedreg comments-open '{"agency":"securities-and-exchange-commission"}'
call fedreg comments-open '{"agency":"commodity-futures-trading-commission"}'

# Search regulatory dockets
call fedreg search '{"query":"cryptocurrency","type":"RULE"}'
call fedreg search '{"query":"digital assets","type":"PRORULE","agency":"treasury-department"}'

# Get specific document details
call fedreg document '{"document_number":"2026-01234"}'
```

### 8. Portfolio Impact Flagging

Automatically surface legislation affecting portfolio companies.

**Process:**
1. When analyzing new legislation, check if any provisions affect:
   - Stablecoin issuers
   - DeFi protocols
   - Custody providers
   - Exchange operators
   - Any specific portfolio company sector
2. Query paradigmdb for relevant holdings:
   ```bash
   call paradigmdb notes_search '{"query":"[sector keyword]"}'
   call paradigmdb db_query '{"query":"SELECT o.name, o.description FROM \"Organization\" o WHERE o.description ILIKE '\''%stablecoin%'\'';"}'
   ```
3. Flag with explanation of potential impact

---

## Jurisdiction Mapping

### Who Has the Pen?

| Issue | Primary Jurisdiction | Key Committees |
|-------|---------------------|----------------|
| Market structure | SEC | Senate Banking, House Financial Services |
| Derivatives | CFTC | Senate/House Agriculture |
| Stablecoins | Mixed (SEC/OCC/Fed) | Banking + Financial Services |
| AML/KYC | FinCEN | Banking, Homeland Security |
| Sanctions | OFAC/Treasury | Banking, Foreign Affairs |
| Tax | Treasury/IRS | Finance, Ways & Means |

### Committee Staff Routing

For a given issue, route to the right staffer:
1. **Committee Counsel** for legislative drafting
2. **Personal Office LD** for member positioning
3. **Leadership Staff** for floor scheduling and whip operations

---

## Internal Accountability

### Log All Hill Interactions

After every Hill meeting or call:
1. Log in Shift as meeting note
2. Record commitments made (by us and by them)
3. Note follow-ups owed
4. Update relevant whip sheet entries
5. Tag portfolio-relevant intel

### Periodic Reports

**Weekly:** Policy team activity summary
**Monthly:** Legislative landscape shifts, whip sheet changes
**Quarterly:** Strategic assessment for leadership

---

## Natural Language Queries

The system should answer questions like:

- "What is Senator X's likely position on the GENIUS Act and why?"
- "Which bills introduced this session could affect our stablecoin portfolio companies?"
- "Who are the key staffers on Senate Banking covering crypto?"
- "What have we heard about stablecoin reserve requirements in the last 90 days?"
- "Generate a briefer for my meeting with Rep Y tomorrow"
- "What is the current whip count on [bill]?"
- "Which states have introduced DeFi-related bills this year?"

---

## Example Session

**User:** Policy briefer for Senator Lummis — meeting tomorrow about stablecoin legislation.

**Agent:**
1. Read Policy Explainer Index first for internal analysis
2. Web search for Senator Lummis profile, recent statements, committee assignments
3. Search internal sources:
   ```bash
   call slack search_messages '{"query":"Lummis"}'
   call gsuite gmail_search '{"query":"Lummis"}'
   call paradigmdb notes_search '{"query":"Lummis"}'
   ```
4. Find current stablecoin legislation status
5. Check portfolio companies in stablecoin space
6. Generate briefer using template

---

## Future Integrations

| Integration | Purpose | Priority |
|-------------|---------|----------|
| Plural Policy API | Bill tracking, momentum scores | High |
| Shift direct integration | Portfolio cross-reference | Medium |
| Regulations.gov API | Docket comments, rulemaking tracking | Medium |
