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

-- App-owned PEM secret for optional OTLP TLS certificate.
-- The Streamlit UI writes the PEM via save_pem_secret; the test SP reads it
-- via _snowflake.get_generic_secret_string().
CREATE SECRET IF NOT EXISTS _internal.otlp_pem_secret
    TYPE = GENERIC_STRING
    SECRET_STRING = '';

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
-- For Streamlit in Native Apps, warehouse references are not supported as
-- QUERY_WAREHOUSE bindings. The Streamlit app uses the consumer session
-- context and can issue USE WAREHOUSE at runtime if needed.
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
    ALLOWED_AUTHENTICATION_SECRETS = (_internal.otlp_pem_secret)
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

CREATE OR REPLACE PROCEDURE app_public.test_otlp_connection_with_secret(endpoint VARCHAR)
RETURNS VARCHAR
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python', 'grpcio', 'validators', 'dnspython')
HANDLER = 'connection_test.test_connection_with_secret'
IMPORTS = ('/python/endpoint_parse.py', '/python/connection_test.py')
EXTERNAL_ACCESS_INTEGRATIONS = (otlp_egress_eai)
SECRETS = ('otlp_pem_cert' = _internal.otlp_pem_secret)
EXECUTE AS OWNER;

CREATE OR REPLACE PROCEDURE app_public.save_pem_secret(pem_content VARCHAR)
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS OWNER
AS
$$
BEGIN
    ALTER SECRET _internal.otlp_pem_secret SET SECRET_STRING = :pem_content;
    MERGE INTO _internal.config AS tgt
    USING (SELECT 'otlp.pem_secret_ref' AS k,
                  CASE WHEN LENGTH(:pem_content) > 0 THEN 'stored' ELSE '' END AS v) AS src
    ON tgt.config_key = src.k
    WHEN MATCHED THEN UPDATE SET config_value = src.v, updated_at = CURRENT_TIMESTAMP()
    WHEN NOT MATCHED THEN INSERT (config_key, config_value) VALUES (src.k, src.v);
    RETURN 'ok';
END;
$$;

CREATE OR REPLACE PROCEDURE app_public.reset_onboarding_dev_state()
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS OWNER
AS
$$
BEGIN
    ALTER SECRET _internal.otlp_pem_secret SET SECRET_STRING = '';

    DELETE FROM _internal.config
    WHERE config_key IN (
        'activation.completed',
        'governance.acknowledged',
        'otlp.endpoint',
        'otlp.pem_secret_ref'
    )
    OR config_key LIKE 'pack_enabled.%';

    RETURN 'ok';
END;
$$;

CREATE OR REPLACE PROCEDURE app_public.get_pem_secret()
RETURNS VARCHAR
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python')
HANDLER = 'secret_reader.get_pem_secret'
IMPORTS = ('/python/secret_reader.py')
EXTERNAL_ACCESS_INTEGRATIONS = (otlp_egress_eai)
SECRETS = ('otlp_pem_cert' = _internal.otlp_pem_secret)
EXECUTE AS OWNER;

GRANT USAGE ON PROCEDURE app_public.provision_otlp_egress(VARCHAR) TO APPLICATION ROLE app_admin;
GRANT USAGE ON PROCEDURE app_public.test_otlp_connection(VARCHAR, VARCHAR) TO APPLICATION ROLE app_admin;
GRANT USAGE ON PROCEDURE app_public.test_otlp_connection_with_secret(VARCHAR) TO APPLICATION ROLE app_admin;
GRANT USAGE ON PROCEDURE app_public.save_pem_secret(VARCHAR) TO APPLICATION ROLE app_admin;
GRANT USAGE ON PROCEDURE app_public.reset_onboarding_dev_state() TO APPLICATION ROLE app_admin;
GRANT USAGE ON PROCEDURE app_public.get_pem_secret() TO APPLICATION ROLE app_admin;

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

-- The PEM certificate is stored in _internal.otlp_pem_secret (app-owned).
-- The save_pem_secret SP writes the PEM; test_otlp_connection_with_secret reads it.
