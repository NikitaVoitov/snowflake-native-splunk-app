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
    MAIN_FILE = '/main.py'
    TITLE = 'Splunk Observability';
GRANT USAGE ON STREAMLIT app_public.main TO APPLICATION ROLE app_admin;

-- Reference callback: binds consumer-granted objects to app references.
-- CONSUMER_WAREHOUSE requires special handling: after binding the reference,
-- resolve the actual warehouse name via SYSTEM$GET_ALL_REFERENCES and set the
-- Streamlit QUERY_WAREHOUSE (warehouse references are not supported by Streamlit).
-- Ref: https://docs.snowflake.com/en/developer-guide/native-apps/requesting-refs
CREATE OR REPLACE PROCEDURE app_public.register_single_callback(
    ref_name STRING, operation STRING, ref_or_alias STRING
)
RETURNS STRING
LANGUAGE SQL
EXECUTE AS OWNER
AS
$$
BEGIN
    CASE (operation)
        WHEN 'ADD' THEN
            SELECT SYSTEM$SET_REFERENCE(:ref_name, :ref_or_alias);
            IF (ref_name = 'CONSUMER_WAREHOUSE') THEN
                LET refs_json VARCHAR := (
                    SELECT SYSTEM$GET_ALL_REFERENCES('CONSUMER_WAREHOUSE', 'TRUE')
                );
                LET wh_name VARCHAR := (
                    SELECT PARSE_JSON(:refs_json)[0]:name::STRING
                );
                IF (wh_name IS NOT NULL) THEN
                    EXECUTE IMMEDIATE
                        'ALTER STREAMLIT app_public.main SET QUERY_WAREHOUSE = ' || wh_name;
                END IF;
            END IF;
        WHEN 'REMOVE' THEN
            SELECT SYSTEM$REMOVE_REFERENCE(:ref_name, :ref_or_alias);
        WHEN 'CLEAR' THEN
            SELECT SYSTEM$REMOVE_ALL_REFERENCES(:ref_name);
        ELSE
            RETURN 'unknown operation: ' || operation;
    END CASE;
    RETURN '';
END;
$$;
GRANT USAGE ON PROCEDURE app_public.register_single_callback(STRING, STRING, STRING)
    TO APPLICATION ROLE app_admin;

-- ─────────────────────────────────────────────────────────────────
-- OTLP gRPC egress: network rule, EAI, app specification, Python SPs
-- Story 2.1 — dynamic host:port via provision_otlp_egress + test_otlp_connection
-- ─────────────────────────────────────────────────────────────────

CREATE NETWORK RULE IF NOT EXISTS _internal.otlp_egress_rule
    TYPE = HOST_PORT
    MODE = EGRESS
    VALUE_LIST = ('placeholder.invalid:4317');

CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION otlp_egress_eai
    ALLOWED_NETWORK_RULES = (_internal.otlp_egress_rule)
    ENABLED = TRUE;

CREATE OR REPLACE PROCEDURE app_public.provision_otlp_egress(endpoint VARCHAR)
RETURNS VARCHAR
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python', 'validators')
HANDLER = 'provision_egress.provision_egress'
IMPORTS = ('/python/endpoint_parse.py', '/python/provision_egress.py')
EXECUTE AS OWNER;

CREATE OR REPLACE PROCEDURE app_public.test_otlp_connection(endpoint VARCHAR, cert_pem VARCHAR)
RETURNS VARCHAR
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python', 'grpcio', 'validators', 'dnspython')
HANDLER = 'connection_test.test_connection'
IMPORTS = ('/python/endpoint_parse.py', '/python/connection_test.py')
EXTERNAL_ACCESS_INTEGRATIONS = (otlp_egress_eai)
EXECUTE AS OWNER;

GRANT USAGE ON PROCEDURE app_public.provision_otlp_egress(VARCHAR) TO APPLICATION ROLE app_admin;
GRANT USAGE ON PROCEDURE app_public.test_otlp_connection(VARCHAR, VARCHAR) TO APPLICATION ROLE app_admin;

-- ─────────────────────────────────────────────────────────────────
-- PEM certificate validation (Story 2.2)
-- Parses a PEM-encoded X.509 certificate server-side, checks the
-- validity window, and returns JSON with expiry/subject/fingerprint.
-- ─────────────────────────────────────────────────────────────────

CREATE OR REPLACE PROCEDURE app_public.validate_otlp_certificate_pem(cert_pem VARCHAR)
RETURNS VARCHAR
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python', 'cryptography')
HANDLER = 'cert_validate.validate_pem'
IMPORTS = ('/python/cert_validate.py')
EXECUTE AS OWNER;

GRANT USAGE ON PROCEDURE app_public.validate_otlp_certificate_pem(VARCHAR)
    TO APPLICATION ROLE app_admin;
