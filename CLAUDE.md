# OCI FinOps Cost Intelligence Platform

## Quick Reference

```bash
# Start local dev stack (PostgreSQL + Grafana)
docker compose up -d

# Run database migrations
python -m etl.pipeline --init-db

# Load sample budget data
docker compose exec postgres psql -U finops -d oci_finops -f /docker-entrypoint-initdb.d/../seed/sample_budgets.sql

# Run ETL pipeline
python -m etl.pipeline                    # incremental load
python -m etl.pipeline --dry-run          # list files without loading
python -m etl.pipeline --backfill         # re-load everything
python -m etl.pipeline --year 2026        # filter by year

# Run anomaly detection
python -m anomaly.runner                  # statistical only
python -m anomaly.runner --ml             # statistical + ML

# Run tests
pytest                                    # all tests
pytest tests/test_focus_parser.py -v      # specific module

# Grafana
# URL: http://localhost:3000 (admin/admin)

# Refresh materialized views (after ETL or manually)
docker compose exec postgres psql -U finops -d oci_finops -c "SELECT refresh_finops_views();"
```

## Architecture

- **ETL**: Python pipeline reads OCI FOCUS reports (.csv.gz) from Object Storage → parses → bulk COPY into PostgreSQL
- **Database**: PostgreSQL 16 with monthly range partitions on `billingperiodstart`, materialized views for dashboard queries
- **Dashboards**: Grafana OSS with 5 auto-provisioned dashboards reading from PostgreSQL
- **Anomaly Detection**: V1 SQL-based (rolling avg + stddev), V2 ML-based (Isolation Forest)
- **Notifications**: OCI ONS + SMTP email for anomaly alerts
- **Infrastructure**: Terraform for OCI (VCN, PostgreSQL DB System, Compute VM, IAM)

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| OCI_TENANCY_OCID | (required) | Tenancy OCID (also used as bucket name) |
| OCI_REGION | us-ashburn-1 | OCI region |
| OCI_CONFIG_FILE | ~/.oci/config | OCI SDK config file path |
| OCI_CONFIG_PROFILE | DEFAULT | OCI config profile |
| PG_HOST | localhost | PostgreSQL host |
| PG_PORT | 5432 | PostgreSQL port |
| PG_DATABASE | oci_finops | Database name |
| PG_USER | finops | Database user |
| PG_PASSWORD | changeme | Database password |
| ETL_BATCH_SIZE | 10000 | Rows per COPY batch |
| FOCUS_REPORT_YEAR | (all) | Filter reports to specific year |

## FOCUS Report Format

- Files stored in OCI Object Storage under namespace `bling`, bucket = tenancy OCID
- Path: `FOCUS Reports/{YYYY}/{MM}/{DD}/*.csv.gz`
- 49 columns following the FinOps FOCUS spec + OCI extensions (x_oci_*)
- Timestamps: ISO 8601 with timezone
- Tags column: JSON object
- Blank values = NULL

## Key Gotchas

- The `billingaccountid` is BIGINT (not text) — OCI uses numeric account IDs
- Column headers in CSVs use mixed case and `x_oci_` prefix for OCI-specific fields
- Materialized views need CONCURRENTLY refresh (requires unique indexes) — the refresh function handles this
- Partitions are pre-created for 2024-2027; extend via the DO block in migration 001
- PostgreSQL `COPY` uses tab delimiters by default; the loader replaces tabs in values with spaces
