---
name: tool-qa
description: "Systematically test all registered tools via the API to find bugs, schema mismatches, and missing credentials. Use when asked to QA tools, test tools, tool audit, tool health check, or verify tool integrations are working."
---

# Tool QA

Systematically test every registered tool (or a subset) via the REST API, find bugs, and produce a structured report with pass/fail results for every method.

## Setup

| Parameter | Default | Example override |
|-----------|---------|-----------------|
| **API URL** | `https://svc-ai.paradigm.xyz` | `http://localhost:8000` |
| **API Key env var** | `API_SECRET_KEY` from `.env` | `MY_API_KEY` |
| **Output directory** | `./tool-qa-output/` | `Output directory: /tmp/qa` |
| **Scope** | All registered tools | `Focus on paradigmdb and slack` |
| **Skip tools** | None | `Skip demo, nano-banana` |

If the user says "QA the tools" or "tool health check", start immediately with defaults. Do not ask clarifying questions unless credentials are missing.

## Workflow

```
1. Discover      List all registered tools via GET /tools
2. Describe      Get method schemas for each tool via GET /tools/{name}
3. Test          Call each method with minimal valid args
4. Classify      Pass / Fail / Skip — with error details
5. Report        Write structured report with summary
```

### 1. Discover

Source the API key and enumerate tools:

```bash
source .env
curl -s "${API_URL}/tools" \
  -H "Authorization: Bearer $API_SECRET_KEY" | python3 -m json.tool
```

### 2. Describe

For each tool (or scoped subset), get the method list and parameter schemas:

```bash
curl -s "${API_URL}/tools/{tool_name}" \
  -H "Authorization: Bearer $API_SECRET_KEY"
```

This returns `{ tool, description, methods: [{ name, description, parameters }] }`.

### 3. Test

For each method, construct a minimal valid request and call it:

```bash
curl -s -X POST "${API_URL}/tools/{tool_name}/{method_name}" \
  -H "Authorization: Bearer $API_SECRET_KEY" \
  -H "Content-Type: application/json" \
  -d '{...}'
```

**Constructing test inputs:**

- For methods with **no required params**: send `{}`
- For methods with **required string params**: use realistic minimal values (e.g., `"BTC"` for a symbol, `"bitcoin"` for a search query)
- For methods with **limit params**: use `2` or `3` to keep responses small
- For methods that are clearly **write/mutate operations** (create, delete, post, send): **SKIP** — do not call them. Mark as `SKIP (write operation)`.
- For methods requiring **IDs from other methods**: chain — call the list method first, extract an ID, then call the detail method

**Classifying results:**

| Result | Criteria |
|--------|----------|
| ✅ PASS | Got a non-error response with plausible data |
| ❌ FAIL (schema) | Column/field name error — the query references columns that don't exist |
| ❌ FAIL (auth) | Authentication or credential error — missing API key, expired token |
| ❌ FAIL (connection) | Can't reach upstream service — timeout, DNS, tunnel down |
| ❌ FAIL (runtime) | Other runtime error — type mismatch, null reference, etc. |
| ⏭️ SKIP | Write operation, or requires complex setup not feasible in automated QA |
| ⚠️ WARN | Returned empty results but no error — may be expected or may indicate a problem |

### 4. Batch Testing

Test tools in groups to stay efficient. Use parallel curl calls for independent tools. After each tool completes, append results to the report immediately (do not batch for the end).

**Order of operations:**
1. Test tools with no external dependencies first (paradigmdb, slack, gsuite)
2. Test tools that depend on external APIs next (twitter, dune, etherscan)
3. Test tools that require special setup last (note and skip if not feasible)

### 5. Report

Copy the report template and fill in results:

```bash
cp {SKILL_DIR}/templates/tool-qa-report-template.md {OUTPUT_DIR}/report.md
```

**After all tests:** Update the summary counts so they match the actual results.

## Issue Investigation

When a method fails, investigate the root cause:

1. **Schema mismatch** — Check the actual database/API schema. The tool may reference columns that were renamed or removed.
2. **Missing credentials** — Check if the required secret exists in 1Password / secret manager.
3. **Connection failure** — Check if the upstream service is reachable (tunnel, firewall, DNS).
4. **Type mismatch** — Check parameter types vs what the upstream expects.

For each failure, note the **root cause** and **suggested fix** in the report.

## Fixing Issues

If you have write access to the tool code:

1. Fix the bug in the tool's `client.py` or `database.py`
2. Commit and push (tools hot-reload on the server)
3. Re-test the fixed method
4. Update the report entry from FAIL to PASS (fixed)

## Guidance

- **Test like an agent would use it.** Call methods with the kind of arguments an LLM would pass.
- **Keep payloads small.** Use `limit: 2` or `3` to avoid huge responses.
- **Never call write/mutate methods.** Only test read operations. If a method name suggests it creates, deletes, posts, or sends something, skip it.
- **Write results incrementally.** Append each tool's results to the report as you go.
- **Chain dependent calls.** If `get_person(id)` needs an ID, first call `list_people(limit=1)` to get one.
- **Note credential issues separately.** Missing credentials are infrastructure issues, not code bugs. Track them in a dedicated section.
- **Don't skip on empty results.** An empty result from a list method is ⚠️ WARN, not a failure. It may mean no data exists yet.
- **Test error recovery.** After a method fails, call another method on the same tool to verify the tool doesn't get stuck (e.g., the aborted transaction bug).

## References

| Reference | When to Read |
|-----------|--------------|
| [references/test-inputs.md](references/test-inputs.md) | Before testing — provides good default test inputs by tool category |

## Templates

| Template | Purpose |
|----------|---------|
| [templates/tool-qa-report-template.md](templates/tool-qa-report-template.md) | Copy into output directory as the report file |
