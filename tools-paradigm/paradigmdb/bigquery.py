"""BigQuery client for Paradigm's custody dashboard views.

The transactions_csv view in custody-dashboard provides the joined transaction data
that combines XTransactionBase with asset and organization info.
"""

import os
from typing import Any

from google.cloud import bigquery

GCP_PROJECT = "custody-dashboard"
DATASET = "shift_prod_public_views"

def get_bigquery_client() -> bigquery.Client:
    """Get a BigQuery client using available credentials.

    Supports both service account JSON and Application Default Credentials (ADC).
    ADC files (from gcloud auth login) have 'account' key; service account files
    have 'client_email' key.

    To set up ADC:
        gcloud auth login svc_ai@paradigm.xyz --update-adc
        gcloud auth application-default set-quota-project ai-svc-485017
    """
    creds_file = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if creds_file and os.path.exists(creds_file):
        import json

        with open(creds_file) as f:
            creds_data = json.load(f)

        if "client_email" in creds_data:
            from google.oauth2 import service_account

            credentials = service_account.Credentials.from_service_account_file(creds_file)
            return bigquery.Client(project=GCP_PROJECT, credentials=credentials)

    # Fall through to ADC (handles both gcloud login ADC and implicit credentials)
    return bigquery.Client(project=GCP_PROJECT)

def query_bigquery(sql: str, limit: int = 100) -> list[dict[str, Any]]:
    """Execute a BigQuery SQL query and return results as list of dicts."""
    client = get_bigquery_client()
    job = client.query(sql)
    results = []
    for row in job.result():
        results.append(dict(row))
        if len(results) >= limit:
            break
    return results

def list_tables() -> list[str]:
    """List all tables/views in the shift_prod_public_views dataset."""
    client = get_bigquery_client()
    tables = client.list_tables(f"{GCP_PROJECT}.{DATASET}")
    return [t.table_id for t in tables]

def describe_table(table_name: str) -> list[dict[str, str]]:
    """Get schema for a table in the dataset."""
    client = get_bigquery_client()
    table = client.get_table(f"{GCP_PROJECT}.{DATASET}.{table_name}")
    return [
        {
            "column_name": field.name,
            "data_type": field.field_type,
            "mode": field.mode,
            "description": field.description or "",
        }
        for field in table.schema
    ]

def get_transactions(
    ticker: str | None = None,
    fund: str | None = None,
    transaction_type: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Query transactions_csv with optional filters."""
    sql = f"SELECT * FROM `{GCP_PROJECT}.{DATASET}.transactions_csv` WHERE 1=1"

    if ticker:
        sql += f" AND UPPER(assetName) = UPPER('{ticker}')"
    if fund:
        sql += f" AND UPPER(fund) LIKE UPPER('%{fund}%')"
    if transaction_type:
        sql += f" AND UPPER(type) LIKE UPPER('%{transaction_type}%')"
    if start_date:
        sql += f" AND executedDate >= '{start_date}'"
    if end_date:
        sql += f" AND executedDate <= '{end_date}'"

    sql += f" ORDER BY executedDate DESC LIMIT {limit}"

    return query_bigquery(sql, limit)
