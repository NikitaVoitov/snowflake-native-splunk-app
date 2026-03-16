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

-- Minimal Streamlit placeholder to satisfy artifacts.default_streamlit.
-- Story 1.3 will replace this with full UI shell/navigation.
CREATE OR REPLACE STREAMLIT app_public.main
    FROM '/streamlit'
    MAIN_FILE = '/main.py';
GRANT USAGE ON STREAMLIT app_public.main TO APPLICATION ROLE app_admin;

-- Callback stubs required by manifest references
CREATE OR REPLACE PROCEDURE app_public.register_single_callback(
    ref_name STRING,
    operation STRING,
    ref_or_alias STRING
)
RETURNS STRING
LANGUAGE SQL
EXECUTE AS OWNER
AS
$$
BEGIN
    RETURN '';
END;
$$;

CREATE OR REPLACE PROCEDURE app_public.get_secret_configuration(ref_name STRING)
RETURNS STRING
LANGUAGE SQL
EXECUTE AS OWNER
AS
$$
BEGIN
    RETURN '';
END;
$$;

CREATE OR REPLACE PROCEDURE app_public.get_eai_configuration(ref_name STRING)
RETURNS STRING
LANGUAGE SQL
EXECUTE AS OWNER
AS
$$
BEGIN
    RETURN '';
END;
$$;

GRANT USAGE ON PROCEDURE app_public.register_single_callback(STRING, STRING, STRING)
TO APPLICATION ROLE app_admin;
GRANT USAGE ON PROCEDURE app_public.get_secret_configuration(STRING)
TO APPLICATION ROLE app_admin;
GRANT USAGE ON PROCEDURE app_public.get_eai_configuration(STRING)
TO APPLICATION ROLE app_admin;
