-- ─────────────────────────────────────────────────────────────────
-- shared_content.sql — Post-deploy script for shared data setup
-- Runs via meta.post_deploy in snowflake.yml after files are staged.
-- Reference: https://docs.snowflake.com/en/developer-guide/snowflake-cli/native-apps/project-definitions
-- ─────────────────────────────────────────────────────────────────
-- In dev mode, the consumer-level grants listed in manifest.yml must
-- be applied explicitly. This script runs as the deploying role
-- (ACCOUNTADMIN) after each `snow app run`.
-- ─────────────────────────────────────────────────────────────────

-- 1. IMPORTED PRIVILEGES — ACCOUNT_USAGE views for source discovery
--    (event tables, custom views, etc.)
GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE
    TO APPLICATION SPLUNK_OBSERVABILITY_DEV_APP;

-- 2. EXECUTE TASK — allow the app-owned role to run scheduled tasks
GRANT EXECUTE TASK ON ACCOUNT
    TO APPLICATION SPLUNK_OBSERVABILITY_DEV_APP;

-- 3. EXECUTE MANAGED TASK — serverless compute for tasks
GRANT EXECUTE MANAGED TASK ON ACCOUNT
    TO APPLICATION SPLUNK_OBSERVABILITY_DEV_APP;

-- 4. CREATE EXTERNAL ACCESS INTEGRATION — OTLP gRPC egress
GRANT CREATE EXTERNAL ACCESS INTEGRATION ON ACCOUNT
    TO APPLICATION SPLUNK_OBSERVABILITY_DEV_APP;
