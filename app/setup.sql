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

-- Durable config/state tables in stateful schemas
CREATE TABLE IF NOT EXISTS _internal.config (
    CONFIG_KEY   VARCHAR(256) NOT NULL,
    CONFIG_VALUE VARCHAR(16384),
    UPDATED_AT   TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT pk_config PRIMARY KEY (CONFIG_KEY)
);

CREATE TABLE IF NOT EXISTS _internal.export_watermarks (
    SOURCE_NAME     VARCHAR(256) NOT NULL,
    WATERMARK_VALUE TIMESTAMP_LTZ NOT NULL,
    UPDATED_AT      TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT pk_export_watermarks PRIMARY KEY (SOURCE_NAME)
);

CREATE TABLE IF NOT EXISTS _metrics.pipeline_health (
    RUN_ID        VARCHAR(36) NOT NULL,
    PIPELINE_NAME VARCHAR(256) NOT NULL,
    SOURCE_NAME   VARCHAR(256) NOT NULL,
    METRIC_NAME   VARCHAR(256) NOT NULL,
    METRIC_VALUE  NUMBER(38, 6),
    METADATA      VARIANT,
    RECORDED_AT   TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS _staging.stream_offset_log (
    _OFFSET_CONSUMED_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

-- Streamlit/health visibility for app_admin
GRANT USAGE ON SCHEMA _internal TO APPLICATION ROLE app_admin;
GRANT USAGE ON SCHEMA _metrics TO APPLICATION ROLE app_admin;
GRANT SELECT, INSERT, UPDATE ON TABLE _internal.config TO APPLICATION ROLE app_admin;
GRANT SELECT ON TABLE _internal.export_watermarks TO APPLICATION ROLE app_admin;
GRANT SELECT ON TABLE _metrics.pipeline_health TO APPLICATION ROLE app_admin;

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
