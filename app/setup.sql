-- ─────────────────────────────────────────────────────────────────
-- setup.sql — Splunk Observability Native App
-- Runs on install and upgrade. Must be idempotent.
-- Reference: https://docs.snowflake.com/en/developer-guide/native-apps/creating-setup-script
-- ─────────────────────────────────────────────────────────────────

-- Application Role — consumer access control
CREATE APPLICATION ROLE IF NOT EXISTS app_admin;

-- Versioned schema — stateless objects (procedures, UDFs, Streamlit)
-- Recreated on each version/upgrade; version pinning protects in-flight tasks.
CREATE OR ALTER VERSIONED SCHEMA app_public;
GRANT USAGE ON SCHEMA app_public TO APPLICATION ROLE app_admin;

-- Stateful schemas — persist across upgrades
CREATE SCHEMA IF NOT EXISTS _internal;
CREATE SCHEMA IF NOT EXISTS _staging;
CREATE SCHEMA IF NOT EXISTS _metrics;

-- TODO: Add tables, procedures, tasks, grants as development progresses
