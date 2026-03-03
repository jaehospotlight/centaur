# Tool QA Report

| Field | Value |
|-------|-------|
| **Date** | {DATE} |
| **API URL** | {API_URL} |
| **Scope** | {SCOPE — e.g., "All tools" or "paradigmdb, slack"} |
| **Total Tools** | {N} |
| **Total Methods** | {N} |

## Summary

| Status | Count |
|--------|-------|
| ✅ Pass | 0 |
| ❌ Fail | 0 |
| ⏭️ Skip | 0 |
| ⚠️ Warn | 0 |
| **Total** | **0** |

### Failing Tools

<!-- List only tools with at least one FAIL. Remove this section if all pass. -->

| Tool | Failing Methods | Root Cause |
|------|----------------|------------|
| {tool_name} | {method1}, {method2} | {brief cause} |

### Missing Credentials

<!-- List tools that fail due to missing secrets/API keys. -->

| Tool | Missing Secret | Where to Add |
|------|---------------|--------------|
| {tool_name} | {SECRET_NAME} | 1Password vault / .env |

## Results by Tool

<!-- One section per tool. Append each tool's results as you test. -->

### {tool_name}

> {tool description from GET /tools/{name}}

| Method | Status | Notes |
|--------|--------|-------|
| `{method_name}` | ✅ PASS | Returned {N} results |
| `{method_name}` | ❌ FAIL (schema) | Column "X" does not exist |
| `{method_name}` | ⏭️ SKIP | Write operation |
| `{method_name}` | ⚠️ WARN | Empty results |

**Failures:**

#### `{method_name}` — {error type}

- **Request:** `POST /tools/{tool}/{method}` with `{args}`
- **Error:** `{error message}`
- **Root cause:** {analysis}
- **Suggested fix:** {what to change and where}
- **Fixed:** ✅ / ❌

---
