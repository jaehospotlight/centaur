---
name: trade-approval
description: "Trade approval workflow for selling assets. Gathers holdings data, runs compliance checks, and drafts Trade Approval Form. Use when asked about selling tokens, trade approvals, or compliance checks for trades."
---

# Trade Approval Skill

Helps traders and trader ops determine asset availability and compliance for sales.

## Usage

User provides asset(s) they want to sell:
```
@ai trade-approval ZORA
@ai trade-approval ME, SNX, HYPE
```

## Workflow

### Step 1: Gather Holdings Data

For each asset, query holdings from custodian APIs (authoritative source for custodian data):

```bash
# Coinbase Prime — query each portfolio
call coinbase get_portfolio_balances '{"portfolio_id":"pf","symbols":["<TICKER>"]}'    # Paradigm Fund
call coinbase get_portfolio_balances '{"portfolio_id":"po","symbols":["<TICKER>"]}'    # Operations
call coinbase get_portfolio_balances '{"portfolio_id":"sp7","symbols":["<TICKER>"]}'   # SP7

# Anchorage Digital
call anchorage get_balances   # then filter for <TICKER>

# Unit410 (self-custody)
call unit410 get_balances     # then filter for <TICKER>
```

For total holdings and liquidity (but NOT custodian breakdown), use BigQuery:
```bash
call paradigmdb bq_query '{"query":"SELECT assetTicker, fundName, holding, liquidity FROM daily_performance_view WHERE assetTicker = '\''<TICKER>'\'' AND day = CURRENT_DATE()"}'
```

**IMPORTANT**: The `daily_performance_view` does NOT have a custodian column. Always use the custodian APIs above to determine where assets are held.

Return holdings in a table:

| Ticker | Total Owned | Available (Unlocked) | Fund | Custodian |
|--------|-------------|----------------------|------|-----------|
| ZORA   | 10,000,000  | 8,500,000            | PF   | Anchorage |
| ZORA   | 2,000,000   | 2,000,000            | P1   | Coinbase  |

**Available** = unlocked, not staked, immediately tradeable

### Step 2: Run Compliance Checks

For each asset, check the following and present results:

#### 2.1 Purchased from Issuer?

**First, check the Token Purchases spreadsheet** (authoritative source for issuer purchases):
https://docs.google.com/spreadsheets/d/1FD0RlpVFOmrrOtv4LUke7OyvzN4Iqsz6GkBLoaGe56A/edit

**IMPORTANT**: This spreadsheet has individual tabs per token (e.g., "NRN", "DYDX", "SNX"). Check if a tab exists for the token ticker:

```bash
call gsuite sheets_read '{"spreadsheet_id":"1FD0RlpVFOmrrOtv4LUke7OyvzN4Iqsz6GkBLoaGe56A","range_notation":"<TICKER>!A1:E10"}'
```

If the tab exists and contains data, the token was purchased/received directly from the issuer. Read the tab to find issuer details and vesting schedule.

If no tab exists, also search Shift notes and deal memos:
```bash
call paradigmdb notes_for_org '{"org_name":"<ORG_NAME>"}'
call gsuite drive_search '{"query":"<TICKER> SAFT"}'
call gsuite drive_search '{"query":"<TICKER> token purchase"}'
```
- **Yes** = received tokens directly from project/foundation (SAFT, token warrant, etc.)
- **No** = purchased on open market (CEX, DEX, OTC from non-issuer)

#### 2.2 Holding Period > 1 Year?
If purchased from issuer, calculate time since TGE (Token Generation Event):
```bash
# First check the Token Purchases spreadsheet tab for TGE/vesting info
# Then search for TGE date online if needed
web_search "<TOKEN_NAME> TGE date token launch"

# Also check first acquisition in our records
call paradigmdb bq_query '{"query":"SELECT MIN(executedDate) as first_acquisition FROM transactions_csv WHERE assetName LIKE '\''%<TICKER>%'\''"}'
```
Compare TGE date to current date. Flag if < 1 year since TGE.

#### 2.3 Cashless Exercise?
Check if tokens came from exercising warrants without paying cash:
```bash
call paradigmdb notes_for_org '{"org_name":"<ORG_NAME>"}'
call gsuite drive_search '{"query":"<TICKER> warrant exercise"}'
```
Look for "cashless exercise" or "net exercise" language.

#### 2.4 >10% Token Supply Ownership?
```bash
call coingecko get_coin '{"coin_id":"<token-id>"}'
# Extract total_supply and circulating_supply from response
```
Calculate: `(our_holdings / total_supply) * 100`
Flag if >= 10%.

#### 2.5 Board Seat?
Check if Paradigm has a board seat or board observer at the company:
```bash
call gsuite drive_search '{"query":"<COMPANY> board seat"}'
call gsuite drive_search '{"query":"<COMPANY> board observer"}'
call paradigmdb notes_for_org '{"org_name":"<ORG_NAME>"}'
```

#### 2.6 Opposite Trades in Past 6 Months?
Check for opposing trades (opposite direction) in the past 6 months:
- **If approving a SELL order** → check for `activity = 'Buy'`
- **If approving a BUY order** → check for `activity = 'Sell'`

```bash
# For SELL orders, check for recent buys:
call paradigmdb bq_query '{"query":"SELECT executedDate, fund, assetName, assetQuantity, assetPriceInUSD, activity FROM transactions_csv WHERE assetName LIKE '\''%<TICKER>%'\'' AND activity = '\''Buy'\'' AND executedDate >= DATE_SUB(CURRENT_DATE(), INTERVAL 6 MONTH)"}'

# For BUY orders, check for recent sells:
call paradigmdb bq_query '{"query":"SELECT executedDate, fund, assetName, assetQuantity, assetPriceInUSD, activity FROM transactions_csv WHERE assetName LIKE '\''%<TICKER>%'\'' AND activity = '\''Sell'\'' AND executedDate >= DATE_SUB(CURRENT_DATE(), INTERVAL 6 MONTH)"}'
```

**Schema reference for `transactions_csv`**:
| Column | Type | Notes |
|--------|------|-------|
| executedDate | DATE | Transaction date |
| assetName | STRING | Asset name (use LIKE '%TICKER%' for matching) |
| activity | STRING | 'Buy' or 'Sell' |
| fund | STRING | Fund name |
| assetQuantity | BIGNUMERIC | Amount |
| assetPriceInUSD | BIGNUMERIC | Price per unit |

### Step 3: Present Compliance Summary

Return compliance checks in a table:

| Check | ZORA | ME | SNX |
|-------|------|-----|-----|
| Purchased from Issuer? | Yes | No | Yes |
| Holding Period > 1 Year? | Yes (Feb 2024) | N/A | No (Aug 2025) |
| Cashless Exercise? | No | N/A | No |
| >10% Token Supply? | No (0.8%) | No (0.1%) | No (2.3%) |
| Board Seat? | No | No | Yes (Observer) |
| Opposite Trades (6mo)? | No | Yes ($50K buy, Oct 2025) | No |

Flag any issues:
- ⚠️ SNX: Holding period < 1 year (acquired Aug 2025)
- ⚠️ SNX: Board observer seat
- ⚠️ ME: Buy trade in past 6 months

### Step 4: Confirm and Update Trade Approval Sheet

After presenting holdings and compliance data, ask user to confirm:
- Which asset(s) to proceed with
- Quantity to sell

Then update the Trade Approval Sheet directly:
https://docs.google.com/spreadsheets/d/1LNzq3reEXR3C6wLlMtyQZ1ATh63E8XtK4VTkdZzWtME/edit?gid=1376060417#gid=1376060417

**Sheet Structure** (Row 1 is header, Row 2 is sub-header):
| Column | Field |
|--------|-------|
| A | Asset |
| B | Transaction Type |
| C | Quantity |
| D | Account Funded |
| E | Token From Issuer |
| F | Time Held >1Yr |
| G | Cashless Exercise |
| H | Greater than 10% of token supply ownership? |
| I | Board Seat? |
| J | Any trades in the opposite direction from the past 6 months? |
| K | Approved |

**To find next empty row and write data:**
```bash
# Read column A to find next empty row
call gsuite sheets_read '{"spreadsheet_id":"1LNzq3reEXR3C6wLlMtyQZ1ATh63E8XtK4VTkdZzWtME","range_notation":"A2:A20"}'

# Write to next empty row (e.g., row 7)
call gsuite sheets_update '{"spreadsheet_id":"1LNzq3reEXR3C6wLlMtyQZ1ATh63E8XtK4VTkdZzWtME","range_notation":"A7:K7","values":[["<TICKER>","Sell","<QTY>","<FUND>","<Yes/No>","<Yes/No/N/A>","<Yes/No>","<No (X%)>","<Yes/No>","<Yes/No>",""]]}'
```

### Step 5: Send Approval Request to Slack

After updating the sheet, send a summary message to the #approvals channel. **Send as a NEW message in the main channel, NOT as a reply in the current thread.** This creates a dedicated approval thread for the trade.

```bash
call slack send_message '{"channel":"#approvals","text":"*Trade Approval Request: <TICKER>*\n\n*Asset:* <TICKER> (<TOKEN_NAME>)\n*Transaction:* Sell <QUANTITY> <TICKER>\n*Fund:* <FUND_NAME>\n*Custodian:* <CUSTODIAN>\n*Notional:* ~$<USD_VALUE> @ $<PRICE>\n\n*Compliance Checks:*\n• Token From Issuer: ✅ <Yes/No>\n• Time Held >1Yr: ✅ <Yes/No/N/A> (TGE: <DATE>)\n• Cashless Exercise: ✅ <Yes/No>\n• >10% Supply: ✅ <No (X%)>\n• Board Seat: ✅ <Yes/No>\n• Opposite Trades (6mo): ✅ <Yes/No>\n\n<https://docs.google.com/spreadsheets/d/1LNzq3reEXR3C6wLlMtyQZ1ATh63E8XtK4VTkdZzWtME/edit?gid=1376060417#gid=1376060417|View Trade Approval Sheet>\n\n<@APPROVER_ID> please approve in thread"}'
```

**Note**: Ask user which approver to tag, or use default approvers for the fund.

### Step 6: Record Approvals in Sheet

**IMPORTANT**: Do NOT pre-populate approval columns (K, L, M, N). WAIT for an approver to actually reply "approved" in the approval thread before recording anything.

**AUTOMATIC TRIGGER**: When a user replies "approved" in an approval thread, immediately record their approval by:

1. **Get the approval message link** from the thread:
```bash
call slack get_thread_replies '{"channel":"<CHANNEL_ID>","thread_ts":"<THREAD_TS>"}'
```

2. **Find the approver's message** and construct the permalink:
```
https://paradigm-ops.slack.com/archives/<CHANNEL_ID>/p<MESSAGE_TS_NO_DOT>?thread_ts=<THREAD_TS>&cid=<CHANNEL_ID>
```
Example: `https://paradigm-ops.slack.com/archives/C0ADWCA25L0/p1770252361656499?thread_ts=1770252299.188729&cid=C0ADWCA25L0`

3. **Find the correct row(s) and column** in the sheet:

**Sheet ID**: `1LNzq3reEXR3C6wLlMtyQZ1ATh63E8XtK4VTkdZzWtME`
**Tab**: `Public Investments ` (note trailing space)

First, read the sheet to find matching rows:
```bash
call gsuite sheets_read '{"spreadsheet_id":"1LNzq3reEXR3C6wLlMtyQZ1ATh63E8XtK4VTkdZzWtME","range_notation":"'\''Public Investments '\''!A:N"}'
```

Match rows by Asset ticker, Transaction Type, Quantity, and Fund from the original approval request message.

**CRITICAL: Row Number Calculation**
The sheet has 2 header rows, so data starts at row 3:
- Row 1 = Header row
- Row 2 = Sub-header row (approver names)
- Row 3 = First data row (JSON index 0)

**Formula**: `sheet_row = json_index + 3`

Examples:
- JSON index 0 → Row 3
- JSON index 5 → Row 8
- JSON index 7 → Row 10

**ALWAYS verify** by matching the Asset, Transaction Type, Quantity, and Fund from the JSON output against the approval request before updating.

**Approver columns** (Row 2 headers):
| Column | Approver |
|--------|----------|
| K | Matt Huang |
| L | Alex Popescu |
| M | Jordan Kong |
| N | Rama Somayajula |

4. **Update the cell(s)** with the approval link:
```bash
call gsuite sheets_update '{"spreadsheet_id":"1LNzq3reEXR3C6wLlMtyQZ1ATh63E8XtK4VTkdZzWtME","range_notation":"'\''Public Investments '\''!M9:M10","values":[["<APPROVAL_LINK>"],["<APPROVAL_LINK>"]]}'
```

5. **Confirm in the thread**:
```
✅ @<approver> approved

Recorded in Trade Approval Sheet.

Still need: @<remaining_approvers> to approve
```

**Approver name mapping**:
| Slack handle | Sheet column |
|--------------|--------------|
| matt, mhuang | K (Matt Huang) |
| alex, apopescu | L (Alex Popescu) |
| jk, jkong | M (Jordan Kong) |
| rama | N (Rama Somayajula) |

## Data Sources

| Data | Primary Source | API Call |
|------|---------------|----------|
| Holdings (by custodian) | **Custodian APIs** (authoritative) | `call coinbase get_portfolio_balances`, `call anchorage get_balances`, `call unit410 get_balances` |
| Holdings (aggregate) | BigQuery | `call paradigmdb bq_query` on `daily_performance_view` |
| Issuer purchases | Token Purchases Sheet (per-token tabs) | `call gsuite sheets_read` on `1FD0RlpVFOmrrOtv4LUke7OyvzN4Iqsz6GkBLoaGe56A` |
| Acquisition dates | BigQuery transactions | `call paradigmdb bq_query` on `transactions_csv` |
| Deal structure | Shift notes | `call paradigmdb notes_for_org` |
| Legal docs | Google Drive | `call gsuite drive_search` |
| Token supply | CoinGecko | `call coingecko get_coin` |
| Prices | CoinGecko | `call coingecko get_price` |
| TGE dates | Web search | `web_search "<TOKEN> TGE date"` |

**Note**: BigQuery `daily_performance_view` columns: `day`, `fundId`, `fundName`, `organizationName`, `assetId`, `assetName`, `assetTicker`, `assetType`, `holding`, `holdingMarketValue`, `liquidity`, `liquidityMarketValue`. There is NO `custodian` column.

## Credentials Required

All credentials are managed server-side by the centaur API. The following must be configured:
- **Coinbase Prime** API keys (for `coinbase` tool) — portfolio access to pf, po, sp7
- **Anchorage Digital** API keys (for `anchorage` tool)
- **Unit410** API keys (for `unit410` tool)
- **Google Workspace** service account `svc_ai@paradigm.xyz` (for `gsuite` tool — Sheets, Drive)
- **CoinGecko Pro** API key (for `coingecko` tool)
- **Slack** bot token (for `slack` tool — send_message, get_thread_replies)

If any tool call returns an auth error, note it and flag which credential needs to be configured.

## Error Handling

- **Asset not found**: Check ticker variations (e.g., HYPE vs HYPE_HYPERCORE)
- **Missing compliance data**: Flag as "Unknown - requires manual review"
- **CoinGecko lookup fails**: Try alternative token ID or use `call coingecko search` first
- **Token Purchases tab not found**: Check alternate ticker names, then search Shift notes
