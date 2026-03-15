# Snowflake Data Governance & Privacy Features — Reference for Splunk Native App

**Purpose:** Comprehensive reference of Snowflake's native data governance, classification, and privacy capabilities that our Snowflake Native App for Splunk can leverage to properly handle sensitive data (PII, compliance data) found within logs, events, traces, and ACCOUNT_USAGE operational telemetry.

**Philosophy:** Our native app is **not** a data classification or privacy enforcement tool. We **rely on the consumer** having classified and protected their sensitive data using Snowflake's native capabilities. We then **query the classification and policy metadata** to understand the consumer's governance posture and adjust our behavior accordingly — ensuring that events, logs, and traces we collect and export to Splunk are handled in accordance with the consumer's defined data governance measures.

**Last verified:** 2026-02-17 against Snowflake official documentation and Snowflake Cortex Search documentation service.

---

## Table of Contents

1. [Snowflake Horizon Catalog — Unified Governance Framework](#1-snowflake-horizon-catalog--unified-governance-framework)
2. [Automated Sensitive Data Classification](#2-automated-sensitive-data-classification)
3. [Object Tagging System](#3-object-tagging-system)
4. [Data Protection Policies](#4-data-protection-policies)
5. [ACCOUNT_USAGE Governance Views](#5-account_usage-governance-views)
6. [Trust Center](#6-trust-center)
7. [Native App Framework & Governance](#7-native-app-framework--governance)
8. [Governance Strategy for Our Native App](#8-governance-strategy-for-our-native-app)
   - 8.1 Core Design Decision: Leverage, Don't Replicate
   - 8.3 ACCOUNT_USAGE — User-Selected Sources (custom view or default view; no app-created views)
   - 8.4 Event Table — User-Selected Sources (governed view or event table; no app-created views)
   - 8.5 Governance Compliance Panel
   - 8.6 ACCESS_HISTORY.policies_referenced — Sensitive Query Identification
   - 8.7 Implementation — Querying Governance Posture
   - 8.8 Summary

---

## 1. Snowflake Horizon Catalog — Unified Governance Framework

**Snowflake Horizon Catalog** is the unified control plane that consolidates data discovery, classification, masking, access control, lineage tracking, and audit capabilities into a single governance architecture. Horizon Catalog is the umbrella under which all the features described in this document operate.

Horizon Catalog is organized into three product areas:
- **Horizon Data Governance** — data discovery, classification, and protection (tags, masking, policies)
- **Horizon Access Management** — fine-grained access control including role-based, user-based, and attribute-based access controls
- **Horizon Analytics & Intelligence** — governance intelligence and compliance reporting

**Key architectural property:** Governance policies defined through Horizon are enforced consistently across **all access methods** — direct SQL queries, Snowpark procedural code, Cortex AI natural language queries (Cortex Analyst), and Streamlit applications. A masking policy applied to a column protects that column regardless of how the data is queried. This eliminates the risk of governance bypass through alternative query interfaces.

**Relevance to our app:** Our stored procedures (owner's rights, running as the app) are subject to the same governance enforcement as any other query. If the consumer has masking policies on columns we read from, those masks are applied to our stored procedure's result sets automatically. We do not need to implement separate redaction — Snowflake enforces it at the platform level.

> **DESIGN DECISION: Leverage, Don't Replicate — User-Owned Governance**
>
> This is a foundational design principle for how our native app handles sensitive data. Snowflake's governance policies are enforced at the **platform layer** — below our application code. Our app **does not auto-create** governed views. **The user is responsible for creating and maintaining governed views** if they want to enforce masking, row access, or projection policies on exported data. The user may already have custom views over ACCOUNT_USAGE or event tables with policies attached; they can select those as the telemetry source. If the user selects a **governed view** (their own) as the source, we stream or read from that view and Snowflake enforces the user's policies. If the user selects the **default ACCOUNT_USAGE view** or the **event table directly**, we work with that source and **inform the user about the risk** (policies cannot be applied to system views or event tables directly). No view auto-creation or sync with source tables/views — the design stays simple; governance is the user's choice.

> **Source:** [Snowflake Horizon Catalog docs](https://docs.snowflake.com/en/guides/horizon), [Getting Started with Horizon for Data Governance](https://www.snowflake.com/en/developers/guides/getting-started-with-horizon-for-data-governance-in-snowflake/)

---

## 2. Automated Sensitive Data Classification

### 2.1 Overview

Snowflake's automated sensitive data classification is a **serverless** feature that uses ML-based analysis to discover and tag columns containing personally identifiable information (PII) or other sensitive data. The system samples column data and metadata, then assigns two classification categories to each identified sensitive column.

The classification process follows three steps: **Analyze** → **Review** → **Apply**.

### 2.2 System Tags

When Snowflake classifies a column as sensitive, it applies two system-defined tags:

| System Tag | Purpose | Possible Values |
|---|---|---|
| `SNOWFLAKE.CORE.SEMANTIC_CATEGORY` | Identifies the **type** of personal/sensitive attribute | EMAIL, NAME, SSN, CREDIT_CARD, PHONE_NUMBER, PASSPORT, etc. (see §2.3 for full list) |
| `SNOWFLAKE.CORE.PRIVACY_CATEGORY` | Identifies the **sensitivity level** | `IDENTIFIER`, `QUASI_IDENTIFIER`, `SENSITIVE` |

**Privacy category definitions:**
- **IDENTIFIER** — Attributes that uniquely identify an individual (e.g., name, SSN, phone number). Synonymous with _direct identifiers_.
- **QUASI_IDENTIFIER** — Attributes that can uniquely identify an individual when **two or more** are combined (e.g., age, gender, ZIP code). Synonymous with _indirect identifiers_.
- **SENSITIVE** — Attributes that do not identify an individual but are information they would prefer not to disclose (currently only: salary).

**Important behavior (2025_02 bundle):** If a user manually sets the value of SEMANTIC_CATEGORY or PRIVACY_CATEGORY on a column, automatic classification **will not overwrite** the user-specified value. This means consumer-curated classifications take precedence over automated results.

### 2.3 Native Semantic Categories — Complete List

Snowflake provides native semantic categories covering common types of sensitive data across multiple geographies.

#### Global Identifiers (PRIVACY_CATEGORY = IDENTIFIER)

| Semantic Category | Notes |
|---|---|
| `BANK_ACCOUNT` | For countries outside CA, NZ, US → subcategory is IBAN |
| `EMAIL` | |
| `IMEI` | International Mobile Equipment Identity |
| `IP_ADDRESS` | |
| `NAME` | |
| `NATIONAL_IDENTIFIER` | Country-specific subcategories (US_SSN, CA_SIN, etc.) |
| `ORGANIZATION_IDENTIFIER` | Business/company identifiers |
| `PAYMENT_CARD` | Credit/debit card numbers |
| `PHONE_NUMBER` | |
| `US_SOCIAL_SECURITY_NUMBER` | US-specific SSN |

#### Country-Specific Identifier Subcategories

| Parent Category | Subcategories | Countries |
|---|---|---|
| `BANK_ACCOUNT` | CA_BANK_ACCOUNT, NZ_BANK_ACCOUNT, US_BANK_ACCOUNT, IBAN | CA, NZ, US, EU |
| `ORGANIZATION_IDENTIFIER` | AU_BUSINESS_NUMBER, AU_COMPANY_NUMBER, SG_UNIQUE_ENTITY_NUMBER | AU, SG |
| `DRIVERS_LICENSE` | AU_DRIVERS_LICENSE, CA_DRIVERS_LICENSE, US_DRIVERS_LICENSE | AU, CA, US |
| `MEDICARE_NUMBER` | AU_MEDICARE_NUMBER, NZ_NHI_NUMBER | AU, NZ |
| `PASSPORT` | AU_PASSPORT, CA_PASSPORT, NZ_PASSPORT, SG_PASSPORT, US_PASSPORT, EU_PASSPORT | AU, CA, NZ, SG, US, EU |
| `PHONE_NUMBER` | AU_PHONE_NUMBER, CA_PHONE_NUMBER, NZ_PHONE_NUMBER, UK_PHONE_NUMBER, US_PHONE_NUMBER | AU, CA, NZ, UK, US |
| `NATIONAL_IDENTIFIER` | US_SSN, CA_SIN, AU_TFN, UK_NHS, SG_NRIC, SG_FIN, EU_NATIONAL_IDENTIFIER | US, CA, AU, UK, SG, EU |
| `TAX_IDENTIFIER` | US_TAX_IDENTIFIER, UK_TAX_IDENTIFIER, AU_TAX_FILE_NUMBER, EU_TAX_IDENTIFIER | US, UK, AU, EU |
| `PAYMENT_CARD` | EU_PAYMENT_CARD (added Jan 2026) | EU |

**EU categories (added January 2026):** DRIVERS_LICENSE, NATIONAL_IDENTIFIER, PASSPORT, PAYMENT_CARD, TAX_IDENTIFIER — enabling automatic identification of GDPR-subject data.

#### Global Quasi-Identifiers (PRIVACY_CATEGORY = QUASI_IDENTIFIER)

| Semantic Category | Notes |
|---|---|
| `AGE` | |
| `COUNTRY` | |
| `DATE_OF_BIRTH` | |
| `ETHNICITY` | |
| `GENDER` | |
| `LATITUDE` | |
| `LONGITUDE` | |
| `MARITAL_STATUS` | |
| `OCCUPATION` | |
| `YEAR_OF_BIRTH` | |
| `US_STATE_OR_TERRITORY` | US-specific |
| `CA_PROVINCE_OR_TERRITORY` | CA-specific |
| `US_CITY`, `US_POSTAL_CODE`, `CA_POSTAL_CODE`, `UK_POSTAL_CODE` | Geographic quasi-identifiers |

#### Sensitive Information (PRIVACY_CATEGORY = SENSITIVE)

| Semantic Category | Notes |
|---|---|
| `SALARY` | Currently the only native SENSITIVE category |

### 2.4 Classification Profiles

A **classification profile** is the configuration container for automated classification. It controls what gets classified, how often, and what happens after classification.

**Key configuration parameters:**

| Parameter | Description |
|---|---|
| `auto_tag` | If `true`, system tags (SEMANTIC_CATEGORY, PRIVACY_CATEGORY) are automatically applied to classified columns |
| `classify_views` | Enable/disable classification of views (not just base tables) |
| `minimum_object_age_for_classification_days` | Days an object must exist before becoming eligible for classification |
| `maximum_classification_validity_days` | Period after which a classified object should be reclassified |
| `snowflake_semantic_categories` | Subset of native categories to classify (if not all) |
| `tag_map` | Mapping from semantic categories to user-defined tags |
| `custom_classifiers` | References to custom classifier instances |

**Classification scope (as of 2025):** Classification profiles can be associated at both **schema level** and **database level**. When set on a database via `ALTER DATABASE`, classification automatically applies to all tables and views within that database. Schema-level profiles take precedence over database-level profiles when both are set.

**SQL to create a classification profile:**
```sql
-- Create a classification profile that auto-tags and maps to custom tags
CREATE OR REPLACE SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE my_db.my_schema.my_profile;

-- Configure the profile
CALL my_db.my_schema.my_profile!SET_CONFIGURATION({
    'auto_tag': true,
    'classify_views': true,
    'minimum_object_age_for_classification_days': 1,
    'maximum_classification_validity_days': 30,
    'tag_map': {
        'column_tag_map': [
            {
                'tag_name': 'my_db.my_schema.pii_tag',
                'tag_value': 'Highly Confidential',
                'semantic_categories': ['NAME', 'NATIONAL_IDENTIFIER', 'PASSPORT']
            },
            {
                'tag_name': 'my_db.my_schema.pii_tag',
                'tag_value': 'Confidential',
                'semantic_categories': ['EMAIL', 'PHONE_NUMBER', 'IP_ADDRESS']
            }
        ]
    }
});
```

### 2.5 Custom Classifiers

For organization-specific sensitive data that Snowflake's native categories don't cover, custom classifiers allow defining regex-based patterns.

```sql
-- Create a custom classifier
CREATE OR REPLACE SNOWFLAKE.DATA_PRIVACY.CUSTOM_CLASSIFIER
    my_db.my_schema.internal_id_classifier;

-- Add a pattern for internal employee IDs (format: EMP-XXXXXX)
CALL my_db.my_schema.internal_id_classifier!ADD_REGEX(
    'INTERNAL_EMPLOYEE_ID',           -- semantic_category
    'IDENTIFIER',                      -- privacy_category
    'EMP-[0-9]{6}',                   -- value_regex
    'EMP',                            -- column_name_regex (optional)
    'HIGH',                           -- confidence
    'Internal employee ID format'     -- description
);

-- List configured patterns
SELECT my_db.my_schema.internal_id_classifier!LIST();
```

Custom classifiers are then referenced in classification profiles via the `custom_classifiers` parameter.

### 2.6 Classification Cost

Classification is a serverless feature consuming Snowflake credits. Monitor costs via:

```sql
-- Classification credit consumption
SELECT start_time, end_time, credits_used
FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY
WHERE service_type = 'SENSITIVE_DATA_CLASSIFICATION'
ORDER BY start_time DESC;
```

> **Sources:** [Introduction to Classification](https://docs.snowflake.com/en/user-guide/classify-intro), [Native Semantic Categories](https://docs.snowflake.com/en/user-guide/classify-native), [Automatic Classification](https://docs.snowflake.com/en/user-guide/classify-auto), [Custom Classifiers](https://docs.snowflake.com/en/user-guide/classify-custom-using), [Jan 2026 EU Categories](https://docs.snowflake.com/en/release-notes/2026/other/2026-01-22-eu-classification)

---

## 3. Object Tagging System

### 3.1 Fundamentals

Snowflake's object tagging system associates metadata key-value pairs with database objects. Tags are defined at the schema level and can be applied to tables, views, schemas, databases, columns, warehouses, and other objects.

**Key constraints:**
- Maximum **50 tags** per object (includes both user-defined and system tags)
- Tags are case-insensitive for lookups but preserve case for display

### 3.2 Tag Inheritance

When a tag is applied to an object higher in the hierarchy, it **automatically propagates to all child objects**:

```
Database (tagged) → Schema → Table → Column
                                       ↑ inherits the database-level tag
```

This dramatically reduces administrative burden. A single tag on a database cascades to all schemas, tables, and columns within it.

### 3.3 Tag Propagation (Automatic)

Tags **automatically propagate** from source objects to derived objects during data movement operations like `CREATE TABLE AS SELECT (CTAS)`. When a derived table is created from a tagged source, the derived table inherits tags from the source. This ensures governance survives data pipelines.

### 3.4 How Tags Were Applied — `apply_method`

Both the ACCOUNT_USAGE TAG_REFERENCES view and the INFORMATION_SCHEMA TAG_REFERENCES function include an `apply_method` column:

| Value | Meaning |
|---|---|
| `CLASSIFIED` | Tag was automatically applied by the sensitive data classification process |
| `MANUAL` | Someone manually set the tag via CREATE or ALTER commands |
| `PROPAGATED` | Tag was automatically propagated from source to derived object |
| `NULL` | Legacy record |
| `NONE` | Legacy record |

**Important:** The ACCOUNT_USAGE.TAG_REFERENCES view **only records direct relationships** — tag inheritance is **not** included in this view. To see inherited tags, use the Information Schema `TAG_REFERENCES` table function instead.

### 3.5 Tag-Based Policy Assignment

Tags enable **automatic policy application**. Instead of assigning masking policies to individual columns, you assign a policy to a tag. Any column tagged with that tag automatically receives the policy:

```sql
-- Create a masking policy
CREATE OR REPLACE MASKING POLICY pii_mask AS (val STRING) RETURNS STRING ->
    CASE
        WHEN IS_ROLE_IN_SESSION('DATA_ADMIN') THEN val
        ELSE '***MASKED***'
    END;

-- Assign the policy to a tag
ALTER TAG my_db.my_schema.pii_tag SET MASKING POLICY pii_mask;

-- Now ANY column tagged with pii_tag automatically gets masked
-- When new columns are added to tagged tables, they inherit the tag and mask automatically
```

This is the **recommended approach** for large-scale governance — it scales to thousands of columns without per-column configuration.

> **Sources:** [Object Tagging Introduction](https://docs.snowflake.com/en/user-guide/object-tagging/introduction), [Tag-Based Masking Policies](https://docs.snowflake.com/en/user-guide/tag-based-masking-policies)

---

## 4. Data Protection Policies

### 4.1 Dynamic Data Masking

**Dynamic data masking** transforms column values at query time based on the executing user's role/context. The underlying data is unchanged — different users see different views of the same data.

**Two application methods:**
1. **Direct masking** — policy assigned to specific columns via `ALTER TABLE ... SET MASKING POLICY`
2. **Tag-based masking** — policy assigned to a tag via `ALTER TAG ... SET MASKING POLICY` (recommended at scale)

**Example — conditional masking with role-based access:**

```sql
CREATE OR REPLACE MASKING POLICY email_mask AS (val STRING) RETURNS STRING ->
    CASE
        WHEN IS_ROLE_IN_SESSION('ADMIN') THEN val
        WHEN IS_ROLE_IN_SESSION('SUPPORT') THEN REGEXP_REPLACE(val, '.+@', '*****@')
        ELSE '***MASKED***'
    END;
```

**Conditional masking** can reference multiple columns from the same table:

```sql
CREATE OR REPLACE MASKING POLICY consent_mask AS (email VARCHAR, consent VARCHAR)
RETURNS VARCHAR ->
    CASE
        WHEN IS_ROLE_IN_SESSION('ADMIN') THEN email
        WHEN consent = 'PUBLIC' THEN email
        ELSE '***MASKED***'
    END;
```

**Masking on semi-structured data (VARIANT/OBJECT):**

```sql
CREATE OR REPLACE MASKING POLICY mask_json_pii AS (val OBJECT) RETURNS OBJECT ->
    CASE
        WHEN IS_ROLE_IN_SESSION('ANALYST') THEN val
        ELSE OBJECT_INSERT(val, 'ssn', '****', true)
    END;
```

**Key property for our app:** Masking policies are enforced automatically on any query, including queries from our stored procedures. If the consumer has masking policies on ACCOUNT_USAGE views they've created (materialized copies), those masks will be applied to our app's reads.

### 4.2 Row Access Policies

**Row access policies** determine which **rows** are visible to different query operators. They return BOOLEAN — `TRUE` means "show this row", `FALSE` means "hide this row".

```sql
CREATE OR REPLACE ROW ACCESS POLICY region_filter AS (region VARCHAR)
RETURNS BOOLEAN ->
    CASE
        WHEN IS_ROLE_IN_SESSION('GLOBAL_MANAGER') THEN TRUE
        WHEN EXISTS (
            SELECT 1 FROM authorized_regions
            WHERE IS_ROLE_IN_SESSION(manager_role) AND region LIKE allowed_region
        ) THEN TRUE
        ELSE FALSE
    END;
```

**Evaluation order:** Row access policies are evaluated **before** masking policies. First rows are filtered, then remaining columns are masked.

**Multiple policies:** When multiple row access policies exist on a table, they combine with **AND** logic — all policies must return TRUE for a row to appear.

### 4.3 Projection Policies

**Projection policies** control whether specific columns can appear in query **output**. Unlike masking (which transforms values), projection policies can completely **block** column projection.

```sql
CREATE OR REPLACE PROJECTION POLICY block_projection AS ()
RETURNS PROJECTION_CONSTRAINT ->
    PROJECTION_CONSTRAINT(ALLOW => false);

-- Conditional: allow only ANALYST role to project
CREATE OR REPLACE PROJECTION POLICY analyst_only AS ()
RETURNS PROJECTION_CONSTRAINT ->
    CASE
        WHEN IS_ROLE_IN_SESSION('ANALYST')
            THEN PROJECTION_CONSTRAINT(ALLOW => true)
        ELSE PROJECTION_CONSTRAINT(ALLOW => false, ENFORCEMENT => 'NULLIFY')
    END;
```

**ENFORCEMENT parameter:**
- `FAIL` — query fails with an error if protected column is projected
- `NULLIFY` — query succeeds but protected column returns NULL for all rows

**Lineage enforcement:** Projection constraints are enforced through the entire column lineage chain. If a base table column is projection-constrained, any view built on that column is also constrained — Snowflake checks the lineage all the way to the base table.

### 4.4 Aggregation Policies

**Aggregation policies** require that queries aggregate results into groups meeting a **minimum group size**, preventing identification of individuals.

```sql
CREATE OR REPLACE AGGREGATION POLICY min_group_5 AS ()
RETURNS AGGREGATION_CONSTRAINT ->
    AGGREGATION_CONSTRAINT(MIN_GROUP_SIZE => 5);

-- Conditional: admins unrestricted, others need min group of 5
CREATE OR REPLACE AGGREGATION POLICY conditional_agg AS ()
RETURNS AGGREGATION_CONSTRAINT ->
    CASE
        WHEN IS_ROLE_IN_SESSION('ADMIN') THEN NO_AGGREGATION_CONSTRAINT()
        ELSE AGGREGATION_CONSTRAINT(MIN_GROUP_SIZE => 5)
    END;
```

When an aggregation policy is active:
- Queries **must** use GROUP BY with aggregate functions (COUNT, SUM, AVG, etc.)
- GROUP BY groups must have at least N rows
- DISTINCT without aggregation is blocked
- ORDER BY on aggregated results is restricted
- Set operations other than UNION ALL are restricted

### 4.5 Policy Application to System Objects

**Critical limitation — system-managed objects:**

| Object Type | Can Apply Policies? | Notes |
|---|---|---|
| User-created tables/views | **Yes** | Full support for all policy types |
| ACCOUNT_USAGE views | **No** | System-managed, read-only. **User option:** Create a user-owned view on top of the ACCOUNT_USAGE view and attach masking, RAP, and projection policies; then select that view as the app's source. See §8.3. |
| Event Tables (user-created) | **Partial** | RAP and projection work; masking is **blocked**. **User option:** Create a custom governed view over the event table, attach policies, and select that view as the app's telemetry source. See §8.4. |
| `SNOWFLAKE.TELEMETRY.EVENTS` (default event table) | **Via EVENTS_VIEW** (RAP only) or **custom view** (full policy support) | See §4.6 and §8.4 |
| Information Schema views | **No** | System-managed |

---

## 5. ACCOUNT_USAGE Governance Views

These are the metadata views our app can query (with `IMPORTED PRIVILEGES ON SNOWFLAKE DB`) to understand the consumer's governance posture.

### 5.1 TAG_REFERENCES

**Schema:** `SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES`
**Latency:** Up to **120 minutes** (2 hours)
**Purpose:** Identifies associations between objects and tags.

**Key columns:**

| Column | Type | Description |
|---|---|---|
| TAG_DATABASE | VARCHAR | Database containing the tag |
| TAG_SCHEMA | VARCHAR | Schema containing the tag |
| TAG_ID | NUMBER | Internal tag identifier (NULL for system tags) |
| TAG_NAME | VARCHAR | Tag name (key in key='value' pair) |
| TAG_VALUE | VARCHAR | Tag value |
| OBJECT_DATABASE | VARCHAR | Database of the tagged object |
| OBJECT_SCHEMA | VARCHAR | Schema of the tagged object |
| OBJECT_ID | NUMBER | Internal object identifier |
| OBJECT_NAME | VARCHAR | Name of the tagged object (or parent table for columns) |
| OBJECT_DELETED | TIMESTAMP_LTZ | When the object was deleted (NULL if active) |
| DOMAIN | VARCHAR | Object type: TABLE, VIEW, SCHEMA, DATABASE, COLUMN, etc. |
| COLUMN_ID | NUMBER | Column identifier (if tag is on a column) |
| COLUMN_NAME | VARCHAR | Column name (if tag is on a column) |
| APPLY_METHOD | VARCHAR | How the tag was applied: CLASSIFIED, MANUAL, PROPAGATED, NULL, NONE |

**Important:** This view only records **direct** tag-to-object relationships. Tag **inheritance** is NOT included. For inherited tags, use `TABLE(INFORMATION_SCHEMA.TAG_REFERENCES(...))`.

**SQL to discover sensitive columns in the consumer's account:**

```sql
-- All columns classified by Snowflake's automated classification
SELECT
    object_database, object_schema, object_name,
    column_name, tag_value AS semantic_category
FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
WHERE tag_name = 'SEMANTIC_CATEGORY'
    AND domain = 'COLUMN'
    AND object_deleted IS NULL
ORDER BY object_database, object_schema, object_name;

-- Columns classified with specific privacy level
SELECT
    object_database, object_schema, object_name,
    column_name, tag_value AS privacy_level
FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
WHERE tag_name = 'PRIVACY_CATEGORY'
    AND domain = 'COLUMN'
    AND tag_value = 'IDENTIFIER'  -- Direct identifiers (most sensitive)
    AND object_deleted IS NULL;

-- How tags were applied (classification vs manual vs propagated)
SELECT apply_method, COUNT(*) AS count
FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
WHERE object_deleted IS NULL
GROUP BY apply_method;
```

### 5.2 POLICY_REFERENCES

**Schema:** `SNOWFLAKE.ACCOUNT_USAGE.POLICY_REFERENCES`
**Latency:** Up to **120 minutes** (2 hours)
**Purpose:** Lists all policy-to-object assignments.
**Supported policy kinds:** aggregation, masking, network, projection, row access, storage lifecycle.

**Key columns:**

| Column | Type | Description |
|---|---|---|
| POLICY_DB | VARCHAR | Database containing the policy |
| POLICY_SCHEMA | VARCHAR | Schema containing the policy |
| POLICY_ID | NUMBER | Internal policy identifier |
| POLICY_NAME | VARCHAR | Policy name |
| POLICY_KIND | VARCHAR(17) | Policy type: AGGREGATION_POLICY, MASKING_POLICY, NETWORK_POLICY, PROJECTION_POLICY, ROW_ACCESS_POLICY, STORAGE_LIFECYCLE_POLICY |
| REF_DATABASE_NAME | VARCHAR | Database of the protected object |
| REF_SCHEMA_NAME | VARCHAR | Schema of the protected object |
| REF_ENTITY_NAME | VARCHAR | Protected object name (table/view) |
| REF_ENTITY_DOMAIN | VARCHAR | Object type (TABLE, VIEW, etc.) |
| REF_COLUMN_NAME | VARCHAR | Protected column name (for column-level policies) |
| TAG_DATABASE | VARCHAR | Tag database (if tag-based policy), else NULL |
| TAG_SCHEMA | VARCHAR | Tag schema (if tag-based policy), else NULL |
| TAG_NAME | VARCHAR | Tag name (if tag-based policy), else NULL |
| POLICY_STATUS | VARCHAR | Status: ACTIVE or error states like MULTIPLE_MASKING_POLICY_ASSIGNED_TO_THE_COLUMN |

**SQL to understand the consumer's protection posture:**

```sql
-- All active masking policies
SELECT
    policy_name, ref_entity_name AS table_name,
    ref_column_name AS column_name, policy_status
FROM SNOWFLAKE.ACCOUNT_USAGE.POLICY_REFERENCES
WHERE policy_kind = 'MASKING_POLICY'
    AND policy_status = 'ACTIVE';

-- All active row access policies
SELECT
    policy_name, ref_entity_name AS table_name, policy_status
FROM SNOWFLAKE.ACCOUNT_USAGE.POLICY_REFERENCES
WHERE policy_kind = 'ROW_ACCESS_POLICY'
    AND policy_status = 'ACTIVE';

-- All active projection policies
SELECT
    policy_name, ref_entity_name AS table_name,
    ref_column_name AS column_name, policy_status
FROM SNOWFLAKE.ACCOUNT_USAGE.POLICY_REFERENCES
WHERE policy_kind = 'PROJECTION_POLICY'
    AND policy_status = 'ACTIVE';

-- Tag-based policies (most scalable governance pattern)
SELECT
    policy_kind, policy_name, tag_name,
    COUNT(*) AS protected_columns
FROM SNOWFLAKE.ACCOUNT_USAGE.POLICY_REFERENCES
WHERE tag_name IS NOT NULL
    AND policy_status = 'ACTIVE'
GROUP BY policy_kind, policy_name, tag_name;
```

### 5.3 DATA_CLASSIFICATION_LATEST

**Schema:** `SNOWFLAKE.ACCOUNT_USAGE.DATA_CLASSIFICATION_LATEST`
**Latency:** Up to **3 hours**
**Purpose:** Most recent classification result for each classified table.

**Key columns:**

| Column | Type | Description |
|---|---|---|
| TABLE_ID | NUMBER | Internal table identifier |
| TABLE_NAME | VARCHAR | Table name |
| SCHEMA_ID | NUMBER | Internal schema identifier |
| SCHEMA_NAME | VARCHAR | Schema name |
| DATABASE_ID | NUMBER | Internal database identifier |
| DATABASE_NAME | VARCHAR | Database name |
| RESULT | VARIANT | Full classification result as JSON (semantic categories, privacy categories, confidence scores per column) |
| STATUS | VARCHAR | `CLASSIFIED` or `REVIEWED` |
| TRIGGER_TYPE | VARCHAR | `MANUAL` or `AUTO CLASSIFICATION` |
| LAST_CLASSIFIED_ON | TIMESTAMP_LTZ | When the table was last classified |

**Pending (2026_01 bundle):** Two new columns will be added:
- `LAST_CLASSIFICATION_ATTEMPT` (TIMESTAMP_LTZ) — timestamp of last classification attempt
- `ERROR_MESSAGE` (VARCHAR) — error message if last attempt failed

**SQL to assess classification coverage:**

```sql
-- Classification coverage across the account
SELECT
    database_name, schema_name, table_name,
    status, trigger_type, last_classified_on
FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_CLASSIFICATION_LATEST
ORDER BY last_classified_on DESC;

-- Tables that have NOT been classified (potential governance gaps)
SELECT t.table_catalog, t.table_schema, t.table_name
FROM SNOWFLAKE.ACCOUNT_USAGE.TABLES t
LEFT JOIN SNOWFLAKE.ACCOUNT_USAGE.DATA_CLASSIFICATION_LATEST dcl
    ON t.table_name = dcl.table_name
    AND t.table_schema = dcl.schema_name
    AND t.table_catalog = dcl.database_name
WHERE dcl.table_name IS NULL
    AND t.deleted IS NULL
    AND t.table_type = 'BASE TABLE';
```

### 5.4 ACCESS_HISTORY

**Schema:** `SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY`
**Latency:** Up to **3 hours**
**Retention:** **365 days** (1 year)
**Purpose:** Tracks detailed data access — who accessed what objects/columns, when, and which policies were enforced.

**Key columns:**

| Column | Type | Description |
|---|---|---|
| QUERY_ID | VARCHAR | Query identifier |
| QUERY_START_TIME | TIMESTAMP_LTZ | When the query started |
| USER_NAME | VARCHAR | User who executed the query |
| DIRECT_OBJECTS_ACCESSED | VARIANT (array) | Objects directly referenced in the query (tables, views, functions) with column-level detail |
| BASE_OBJECTS_ACCESSED | VARIANT (array) | Underlying base tables (even when querying views) |
| OBJECTS_MODIFIED | VARIANT (array) | Objects written to (INSERT, UPDATE, DELETE, CTAS) |
| OBJECT_MODIFIED_BY_DDL | VARIANT | DDL changes (including policy assignments, tag updates) |
| **POLICIES_REFERENCED** | VARIANT (array) | **Masking and row access policies enforced during query execution** |
| PARENT_QUERY_ID | VARCHAR | Parent query ID (for nested queries) |
| ROOT_QUERY_ID | VARCHAR | Root query ID |

**The `policies_referenced` column is critical** — it records which masking and row access policies were actually enforced for each query. This allows our app to:
- Identify queries that accessed policy-protected data
- Understand which policies are actively protecting sensitive data
- Audit compliance without needing to manually join TAG_REFERENCES + POLICY_REFERENCES + QUERY_HISTORY

**SQL for sensitive data access monitoring:**

```sql
-- Queries that triggered masking or row access policies today
SELECT
    user_name, query_id, query_start_time,
    policies_referenced
FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY
WHERE ARRAY_SIZE(policies_referenced) > 0
    AND query_start_time >= CURRENT_DATE()
ORDER BY query_start_time DESC;
```

### 5.5 OBJECT_DEPENDENCIES

**Schema:** `SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES`
**Latency:** Up to **3 hours**
**Purpose:** Records dependencies between objects (views → tables, functions → tables, etc.) for lineage tracking.

**Key columns:**

| Column | Type | Description |
|---|---|---|
| REFERENCED_DATABASE | VARCHAR | Base object database |
| REFERENCED_SCHEMA | VARCHAR | Base object schema |
| REFERENCED_OBJECT_NAME | VARCHAR | Base object name |
| REFERENCED_OBJECT_DOMAIN | VARCHAR | Base object type |
| REFERENCING_DATABASE | VARCHAR | Dependent object database |
| REFERENCING_SCHEMA | VARCHAR | Dependent object schema |
| REFERENCING_OBJECT_NAME | VARCHAR | Dependent object name |
| REFERENCING_OBJECT_DOMAIN | VARCHAR | Dependent object type |

**Note:** This view tracks only **reference-based** dependencies (views referencing tables, etc.). It does **not** track data movement dependencies like CTAS or INSERT operations.

### 5.6 Additional Governance Views

| View | Purpose | Latency |
|---|---|---|
| `MASKING_POLICIES` | Catalog of all masking policies in the account | 2 hours |
| `ROW_ACCESS_POLICIES` | Catalog of all row access policies | 2 hours |
| `PROJECTION_POLICIES` | Catalog of all projection policies | 2 hours |
| `TAGS` | Catalog of all tags in the account | 2 hours |

### 5.7 System Functions & Commands for Governance Posture

These are NOT ACCOUNT_USAGE views, but complement them for governance posture assessment:

**`SYSTEM$SHOW_SENSITIVE_DATA_MONITORED_ENTITIES()`** — Returns a JSON array of databases/schemas associated with classification profiles (i.e., monitored by auto-classification):

```sql
-- Show all databases monitored by auto-classification
SELECT SYSTEM$SHOW_SENSITIVE_DATA_MONITORED_ENTITIES('DATABASE');
-- Returns: [{"name":"TESTDB","type":"DATABASE","profile_name":"TESTDB.TESTSCHEMA.MY_PROFILE"}, ...]

-- Show all monitored entities (databases + schemas)
SELECT SYSTEM$SHOW_SENSITIVE_DATA_MONITORED_ENTITIES();
```

> **Note:** This function is in Preview (as of Jul 2025). The current role must have access to both the entity and the associated classification profile.

**`SHOW SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE`** — Lists all classification profile instances in the account:

```sql
SHOW SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE IN ACCOUNT;
```

**`<profile>!DESCRIBE()`** — Returns the full configuration of a classification profile (auto_tag, tag_map, custom_classifiers):

```sql
SELECT my_db.my_schema.my_profile!DESCRIBE();
-- Returns JSON: {"auto_tag": true, "column_tag_map": [...], "custom_classifiers": {...}}
```

> **Important:** Calling `DESCRIBE()` on a classification profile requires the `<profile>!PRIVACY_USER` instance role. Our app would need the consumer to grant this if we want to show profile configuration details.

> **Sources:** [TAG_REFERENCES](https://docs.snowflake.com/en/sql-reference/account-usage/tag_references), [POLICY_REFERENCES](https://docs.snowflake.com/en/sql-reference/account-usage/policy_references), [DATA_CLASSIFICATION_LATEST](https://docs.snowflake.com/en/sql-reference/account-usage/data_classification_latest), [ACCESS_HISTORY](https://docs.snowflake.com/en/sql-reference/account-usage/access_history), [SYSTEM$SHOW_SENSITIVE_DATA_MONITORED_ENTITIES](https://docs.snowflake.com/en/sql-reference/functions/system_show_sensitive_data_monitored_entities), [CLASSIFICATION_PROFILE](https://docs.snowflake.com/en/sql-reference/classes/data_privacy/classification_profile)

---

## 6. Trust Center

**Snowflake Trust Center** is the centralized web interface for security and compliance management.

### 6.1 Components

- **Security Hub** — unified view of security controls, access policies, threat detection across all accounts in an organization
- **Compliance Center** — self-service portal for compliance certifications and audit reports (SOC 2 Type II, ISO 27001, HIPAA, FedRAMP, etc.)
- **Data Security Dashboard** — tiles showing:
  - Number of databases monitored by classification
  - Number of tables classified
  - Number of sensitive columns discovered
  - Distribution across privacy categories (identifiers, quasi-identifiers, sensitive)

### 6.2 Trust Center for Classification

The Trust Center provides a **web-based interface** for:
- Configuring sensitive data classification (creating profiles, setting scope)
- Viewing classification results dashboards
- Managing data security policies
- Monitoring governance posture without requiring SQL

**Setting up classification via Trust Center:**
1. Navigate to Trust Center → Data Security
2. Create a classification profile
3. Associate databases/schemas with the profile
4. Review classification results in the dashboard

> **Sources:** [Snowflake Security Hub](https://www.snowflake.com/en/why-snowflake/snowflake-security-hub/), [Trust Center](https://trust.snowflake.com)

---

## 7. Native App Framework & Governance

### 7.1 Accessing Governance Metadata

Our native app can access governance metadata through ACCOUNT_USAGE views when the consumer grants `IMPORTED PRIVILEGES ON SNOWFLAKE DB`:

```
IMPORTED PRIVILEGES ON SNOWFLAKE DB
    → Access to ACCOUNT_USAGE schema
        → TAG_REFERENCES          (what's tagged/classified)
        → POLICY_REFERENCES       (what policies are applied)
        → DATA_CLASSIFICATION_LATEST  (classification results)
        → ACCESS_HISTORY          (who accessed what, with policy info)
        → OBJECT_DEPENDENCIES     (data lineage)
        → MASKING_POLICIES        (policy catalog)
        → ROW_ACCESS_POLICIES     (policy catalog)
        → PROJECTION_POLICIES     (policy catalog)
```

This privilege is **already required** by our app for accessing ACCOUNT_USAGE views like QUERY_HISTORY, TASK_HISTORY, etc. — so no additional privilege is needed to also read governance metadata.

### 7.2 Blocked Context Functions in Native Apps

**Critical consideration:** The Native App Framework **blocks certain context functions** in stored procedures and UDFs owned by the app:

| Context Function | Blocked in Shared Content | Blocked in App's Procedures |
|---|---|---|
| `CURRENT_ROLE` | Returns NULL | — |
| `CURRENT_ROLE_TYPE` | Returns NULL | — |
| `CURRENT_USER` | Returns NULL | — |
| `CURRENT_SESSION` | Returns NULL | — |
| `IS_ROLE_IN_SESSION` | Returns NULL | — |
| `CURRENT_IP_ADDRESS` | Returns NULL | Throws exception |
| `CURRENT_AVAILABLE_ROLES` | Returns NULL | Throws exception |
| `CURRENT_SECONDARY_ROLES` | Returns NULL | Throws exception |
| `ALL_USER_NAMES` | — | Throws exception |
| `CURRENT_WAREHOUSE` | — | Throws exception |

**Impact on governance policies:** Masking policies and row access policies that use `CURRENT_ROLE()` or `IS_ROLE_IN_SESSION()` will receive NULL for these functions when data is accessed through our app's shared content (like views). For stored procedures running as EXECUTE AS OWNER, the app's own role context is used — but the consumer's role-based policies will evaluate against the **app's role**, not the end user's role.

**Implication:** Our app cannot create masking policies that differentiate based on the end user's role. However, Snowflake's governance policies applied by the consumer to their own data will still be enforced when our stored procedures read that data — the enforcement happens at the data layer, not the application layer.

### 7.3 Applying Policies to App-Owned Objects

Our app **can** apply governance policies to its own internal tables (config, metrics, pipeline health) — the ones the app owns and manages. We do **not** create intermediate/staging copies of ACCOUNT_USAGE data (our serverless tasks read, transform, and export directly to Splunk without intermediate storage).

Masking policies on app-owned tables are useful for protecting configuration data (e.g., ensuring HEC tokens stored in Snowflake Secrets are never exposed in query results from config tables):

```sql
-- Masking policy on app-owned config table to protect sensitive settings
CREATE OR REPLACE MASKING POLICY _internal.mask_config_values
    AS (val VARCHAR, key_name VARCHAR) RETURNS VARCHAR ->
    CASE
        WHEN key_name LIKE '%token%' OR key_name LIKE '%secret%' THEN '***REDACTED***'
        ELSE val
    END;
```

### 7.4 References and Tags/Policies

When our app accesses consumer objects through the **reference mechanism**, any tags and policies on those objects are respected automatically. The reference does not bypass governance — it simply provides a handle for the app to use, and Snowflake enforces all policies at query time.

**For tags and policies on referenced databases:** If our app package uses objects from a database containing tags or policies, the provider must grant `REFERENCE_USAGE` on that database to the application package:
```sql
GRANT REFERENCE_USAGE ON DATABASE <db_name>
    TO SHARE IN APPLICATION PACKAGE <app_package>;
```

> **Sources:** [Native App Access to Objects](https://docs.snowflake.com/en/developer-guide/native-apps/requesting-about), [Blocked Context Functions](https://docs.snowflake.com/en/developer-guide/native-apps/security-about), [Tags and Policies in Native Apps](https://docs.snowflake.com/en/release-notes/bcr-bundles/2023_07/bcr-1274)

---

## 8. Governance Strategy for Our Native App

### 8.1 Core Design Decision: Leverage, Don't Replicate — No Auto-Creation of Views

> **This is a foundational design decision for sensitive data handling.**

Our app does **not** implement its own data classification or privacy enforcement engine. Snowflake's governance policies are enforced at the **platform layer** — below our application code. Our app **does not auto-create** governed views. **The user is responsible for creating governed views** (and attaching masking, row access, or projection policies) if they want to maintain governance standards. The user may already have custom views over ACCOUNT_USAGE or event tables; we do not create an additional view layer.

**Data flow:**

- **Event Tables:** If the user selects a **governed view** as the telemetry source, we stream from that view (Snowflake enforces the user's policies). If the user selects the **event table** directly, we stream from the event table; we **inform the user** that masking cannot be applied on event tables and they may want to use a custom view for governance.
- **ACCOUNT_USAGE:** If the user selects a **custom view** (with policies attached) as the source, we read from that view. If the user selects the **default ACCOUNT_USAGE view**, we read from it directly; we **inform the user** that policies cannot be applied to system views and they may want to use a custom view for governance.

Our serverless tasks work with **whatever source the user selected** — no view sync, no app-owned governed views to maintain.

**What this means in practice:**

1. **Encourage** consumers to classify their sensitive data using Snowflake's native capabilities (classification profiles, custom classifiers, Trust Center)
2. **Query** classification and policy metadata to understand what the consumer has protected
3. **Respect** the consumer's governance posture — Snowflake enforces policies automatically when we read from their governed views
4. **Inform** the user when they select a non-governed source (default ACCOUNT_USAGE view or event table) about the governance risk — no auto-creation, just clear guidance

### 8.2 Data Sources and Governance Considerations

#### ACCOUNT_USAGE Views (Performance Pack, Cost Pack, Security Pack)

> **User-selected source:** For each ACCOUNT_USAGE source, the user selects either a **custom view** (their own, with masking/row access/projection policies attached) or the **default ACCOUNT_USAGE view**. Our serverless tasks read from the selected source. We **do not** create or maintain governed views. If the user selects the default view, we **inform them** that policies cannot be applied to system views and that they can create a custom view to enforce governance. See §8.3.

| Data Source | Sensitive Data Risk | User Option | When Default Selected |
|---|---|---|---|
| `QUERY_HISTORY` | **High** — `QUERY_TEXT` may contain literal PII | User can create a custom view over QUERY_HISTORY and attach masking on QUERY_TEXT; select that view as source | We inform user: QUERY_TEXT may contain PII; consider a custom view with masking |
| `LOGIN_HISTORY` | **Medium** — user names, IP addresses | User can use a custom view with policies; select as source | We inform user of governance limitation |
| `ACCESS_HISTORY` | **Medium** — `policies_referenced` valuable (see §8.6) | User can use custom view with policies if needed | Inform if sensitive |
| `TASK_HISTORY`, `COMPLETE_TASK_GRAPHS`, `LOCK_WAIT_HISTORY`, etc. | **Low** — operational metadata | User may use default view or their own view | Typically low risk; inform as needed |
| `SESSIONS` | **Medium** — session metadata, IPs | User can use custom view with masking/RAP | We inform user of governance limitation |

#### Event Tables (Distributed Tracing Pack)

| Data Source | Sensitive Data Risk | User Option | When Event Table Selected |
|---|---|---|---|
| Event Table (default or user-created) | **Variable** — depends on application logs | User can select **their governed view** (with RAP + masking) as telemetry source, or the **event table** directly | We stream from event table; **inform user** that masking is blocked on event tables — use a custom view if they need value-level redaction. See §8.4 |
| Span/log attributes (RECORD, RECORD_ATTRIBUTES, VALUE) | **High** — may contain PII | If user uses a governed view, they attach masking to RECORD, RECORD_ATTRIBUTES, VALUE on that view | If streaming from event table, we inform about risk |

### 8.3 ACCOUNT_USAGE — User-Selected Sources (No App-Created Views)

#### Design Decision: User Selects Source — Custom View or Default View

> **DECISION:** We **do not** create or maintain governed views. For each ACCOUNT_USAGE source (QUERY_HISTORY, TASK_HISTORY, LOGIN_HISTORY, etc.), the **user selects** the data source: either their **own custom view** (with masking, row access, or projection policies attached) or the **default ACCOUNT_USAGE view**. Our serverless tasks read from the selected source. If the user selects the default view, we **inform them** that policies cannot be applied to system views and that creating a custom view is the way to enforce governance — that's it. No auto-creation, no view sync.

#### Why a Custom View Helps (User Guidance)

Policies cannot be applied to `ACCOUNT_USAGE` views directly (they are system-managed). For example, `QUERY_TEXT` in QUERY_HISTORY may contain literal PII embedded in SQL; masking cannot be applied to the system view. **If the user wants governance**, they create a user-owned view on top of the ACCOUNT_USAGE view and attach masking, row access, or projection policies to that view. They then **select that view** as the app's source. Snowflake enforces the user's policies when our pipeline reads from it.

**Architecture when user selects a custom view:**

```
User's custom view (e.g. my_schema.my_query_history with masking on QUERY_TEXT)
    ↓
Poll-based pipeline reads from selected source → Transform → HEC → Splunk
```

**Architecture when user selects default ACCOUNT_USAGE view:**

```
SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY (or other)
    ↓
Poll-based pipeline reads from selected source → Transform → HEC → Splunk
    + We inform user: policies cannot be applied to this source; consider a custom view for governance.
```

#### What the User Can Do (Their Own Views)

If the user creates a custom view over ACCOUNT_USAGE and selects it as the source:

1. **Attach a masking policy** on high-risk columns (e.g. QUERY_TEXT) — e.g. regex-based PII scrubbing, or full redaction.
2. **Add a row access policy** — e.g. exclude certain users, databases, or query tags.
3. **Apply projection policies** — control which columns are visible.
4. **Tag-based masking** — if they use sensitivity tags, tag-based policies are enforced automatically when we read from their view.

**Blocked context functions (see §7.2):** In the Native App context, `IS_ROLE_IN_SESSION()`, `CURRENT_ROLE()` return NULL. Masking policies that rely on these will always take the "else" branch. For export pipelines, unconditional masking (e.g. regex scrub or full redact) is the typical approach.

#### Streamlit UI: ACCOUNT_USAGE Configuration

The ACCOUNT_USAGE configuration in our Streamlit UI must:

1. **Per-source selection**: For each ACCOUNT_USAGE source in the enabled packs, let the user choose: **custom view** (they specify the view name) or **default ACCOUNT_USAGE view**.
2. **Risk notice**: When the user selects a default ACCOUNT_USAGE view, show a clear notice: *Policies cannot be applied to system views. To enforce masking or row access, create a custom view over this source, attach your policies, and select that view here.*
3. **Optional: show policies on selected view**: If the selected source is a custom view, we can query `INFORMATION_SCHEMA.POLICY_REFERENCES` to show which masking/RAP/projection policies are attached (informational only).
4. **No "Rebuild Views" or app-created views**: We do not create or recreate any views.

#### ACCESS_HISTORY as Complementary Signal

- ACCESS_HISTORY shows which objects and columns were accessed; `policies_referenced` (see §8.6) shows which policies were enforced.
- Our Security Pack (post-MVP) can export ACCESS_HISTORY to Splunk; the user would select their custom view or the default view, with the same risk-inform approach if default is selected.

```
┌─────────────────────────────────────────────────────────────────┐
│ ACCOUNT_USAGE — Select Source per Pack                           │
├─────────────────────────────────────────────────────────────────┤
│ For each source, choose: your custom view (with policies)         │
│ or the default ACCOUNT_USAGE view.                               │
│                                                                  │
│ QUERY_HISTORY:  [ my_schema.my_query_history ▾ ]  (custom view)  │
│   Policies on view: masking on QUERY_TEXT                        │
│   Or: [ SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY ] → ⚠ No policies  │
│       possible on system view; we'll export as-is. Consider      │
│       a custom view to enforce governance.                       │
│                                                                  │
│ TASK_HISTORY:   [ SNOWFLAKE.ACCOUNT_USAGE.TASK_HISTORY ▾ ]       │
│   ⓘ Default selected — no governance policies on this source.   │
└─────────────────────────────────────────────────────────────────┘
```

### 8.4 Event Table — User-Selected Sources (No App-Created Views)

#### Design Decision: User Selects Telemetry Source — Governed View or Event Table

> **DECISION:** We **do not** create or maintain governed views over event tables. The **user selects** the telemetry source: either their **own governed view** (a custom view over an event table, with masking/row access policies attached) or the **event table** directly. We stream from the selected source. If the user selects a governed view, we create the stream on that view and Snowflake enforces the user's policies. If the user selects the event table directly, we stream from the event table and **inform the user** that masking policies cannot be applied on event tables — they may want to use a custom view for value-level redaction. That's it. No auto-creation of views, no sync with source tables.

> **Full research and live test results:** See [Event Table Streams & Governance Research](event_table_streams_governance_research.md)

**Governance constraints on event tables (for user guidance):**

| Policy Type | Directly on Event Table | On User's Custom View |
|---|---|---|
| **Masking policies** | **BLOCKED** (`INVALID OPERATION FOR EVENT TABLES`) | **Works** |
| **Row access policy** | Works (user-created only; not default) | **Works** |
| **Projection policy** | Works (user-created only; not default) | **Works** |
| **Stream creation** | Works | **Works** (stream on view) |

Masking is **blocked on all event tables**. If the user wants value-level redaction (e.g. strip PII from log messages), they must create their own custom view over the event table, attach masking policies to that view, and **select that view** as the app's telemetry source.

#### Architecture: User-Selected Source → Stream → Task → Splunk

**When user selects a governed view:**

```
User's governed view (over event table, with RAP + masking)
    ↓
Stream (APPEND_ONLY on view) → Task → Splunk
```

**When user selects event table directly:**

```
Event Table
    ↓
Stream (APPEND_ONLY on table) → Task → Splunk
    + We inform user: masking cannot be applied on event tables; consider a custom view for governance.
```

Our serverless tasks work with whatever source the user selected. No app-created views to maintain.

#### Key Limitations (When User Uses Their Own View + Stream)

If the user selects a **governed view** as the source and we create a stream on it, the following apply to **their view** (user responsibility):

| Limitation | Severity | User Guidance |
|---|---|---|
| `CREATE OR REPLACE VIEW` **breaks all streams** on the view (offset lost) | **CRITICAL** | Use `ALTER VIEW` for policy changes; never `CREATE OR REPLACE` after the stream exists. |
| View must use **simple SQL only** (no GROUP BY, DISTINCT, LIMIT, UDFs) for stream compatibility | **MEDIUM** | Keep the view a simple column pass-through; we document schema requirements. |
| Stream schema (offset log) must match the **view** schema | **MEDIUM** | Our pipeline aligns to the selected source schema (view or event table). |
| Staleness / retention | **MEDIUM** | For default event table, retention cannot be altered; consume stream frequently. For user-created event tables, user can set retention. |

> **Operational best practices:** See [Event Table Streams & Governance Research](event_table_streams_governance_research.md#operational-best-practices-for-pattern-c) (applies when user provides a governed view).

#### Streamlit UI: Event Table Configuration

The Event Table configuration panel must:

1. **Source selection**: Let the user choose the telemetry source — **their governed view** (they specify the view name) or the **event table** directly (default or user-created).
2. **Risk notice**: When the user selects an event table directly, show: *Masking policies cannot be applied on event tables. To redact sensitive data in RECORD, RECORD_ATTRIBUTES, or VALUE, create a custom view over this event table, attach masking policies, and select that view as the source.*
3. **Optional**: If the source is a custom view, show which policies are attached (from POLICY_REFERENCES).
4. **Stream health**: When a stream exists (on view or table), show staleness status and warn if approaching stale.
5. **No app-created views**: We do not create governed views; we stream from the user's selected source.

#### Span/Log Attribute Sensitivity (User Guidance)

RECORD, RECORD_ATTRIBUTES, and VALUE may contain PII. If the user streams from the **event table** directly, we cannot apply masking there — we inform them of the risk. If they use a **governed view**, they attach masking policies to that view's RECORD, RECORD_ATTRIBUTES, and/or VALUE columns.

> **Consumer Guidance (shown in Streamlit UI):** If your applications log sensitive data in span attributes, log messages, or metric payloads, use a custom view over your event table and attach masking policies to RECORD, RECORD_ATTRIBUTES, and/or VALUE, then select that view as the telemetry source.

Example masking policies (user applies to their view):
```sql
-- Masking policy to redact sensitive keys in RECORD (structured span/log fields)
CREATE OR REPLACE MASKING POLICY mask_log_content
    AS (val OBJECT) RETURNS OBJECT ->
    CASE
        WHEN IS_ROLE_IN_SESSION('SPLUNK_EXPORT_ROLE') THEN val
        ELSE OBJECT_DELETE(OBJECT_DELETE(val, 'user.email'), 'user.ssn')
    END;

ALTER VIEW <user_schema>.<user_governed_events_view>
    ALTER COLUMN RECORD SET MASKING POLICY mask_log_content;

-- Masking policy to redact PII patterns in VALUE (log message text, metric payloads)
CREATE OR REPLACE MASKING POLICY mask_value_content
    AS (val VARIANT) RETURNS VARIANT ->
    CASE
        WHEN IS_ROLE_IN_SESSION('SPLUNK_EXPORT_ROLE') THEN val
        ELSE REGEXP_REPLACE(val::VARCHAR,
            '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}',
            '***@redacted.com')::VARIANT
    END;

ALTER VIEW <user_schema>.<user_governed_events_view>
    ALTER COLUMN VALUE SET MASKING POLICY mask_value_content;
```

### 8.5 Governance Compliance Panel

Our Streamlit UI should include a **Governance Compliance** panel that demonstrates our app fully **honors and respects** the consumer's existing data governance, privacy measures, and protection posture. This is NOT a duplicate of the Trust Center dashboard — we do not show raw classification statistics. Instead, we show how our app's behavior aligns with what the consumer has configured.

**Purpose:** Communicate to the consumer that our app is governance-aware and adapts its behavior based on their configured policies. Build trust.

**When default views or event tables are selected:** The panel **must inform the user** that masking and row access policies cannot be applied to those sources (system ACCOUNT_USAGE views and event tables do not support policy attachment). To enforce governance on exported data, the user has to create their own custom views (with masking/row access policies) over those sources and select those custom views as the telemetry source in the app.

**Data sources for the panel (all via pure SQL against ACCOUNT_USAGE views):**

| API / View | What We Extract | Purpose |
|---|---|---|
| `SYSTEM$SHOW_SENSITIVE_DATA_MONITORED_ENTITIES()` | Databases/schemas with active classification profiles | Show that we know classification is active |
| `SHOW SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE` | List of classification profiles configured | Show profile awareness |
| `TAG_REFERENCES` (system tags only) | Count of SEMANTIC_CATEGORY and PRIVACY_CATEGORY tags applied | Show we see what's classified |
| `POLICY_REFERENCES` | Active masking, row access, projection policies | Show we honor these policies |
| `DATA_CLASSIFICATION_LATEST` | Classification profile names referenced in results | Show classification profiles are running |
| `ACCESS_HISTORY.policies_referenced` | Policies actively enforced on queries | Show real-time enforcement awareness |

**Panel wireframe:**

```
┌─────────────────────────────────────────────────────────────────┐
│ Governance Compliance                                            │
│ Our app honors your Snowflake data governance configuration      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│ Classification Awareness:                                        │
│   ✓ Auto-classification active on 3 databases                   │
│   ✓ 2 classification profiles detected                          │
│   ✓ 1 custom classifier in use                                  │
│   ✓ Semantic categories in use: EMAIL, NAME, PHONE_NUMBER,      │
│     SSN, CREDIT_CARD, IP_ADDRESS (+ 4 more)                    │
│                                                                  │
│ Active Protection Honored by This App:                           │
│   ✓ 12 masking policies (including 3 tag-based)                 │
│   ✓ 4 row access policies                                      │
│   ✓ 2 projection policies                                      │
│   All policies are enforced automatically by Snowflake when     │
│   this app reads data from your account.                        │
│                                                                  │
│ Selected Export Sources:                                          │
│                                                                  │
│   QUERY_HISTORY → my_schema.my_query_history (custom view)       │
│     Masking on QUERY_TEXT; row access: 1 policy                  │
│     Or: default ACCOUNT_USAGE.QUERY_HISTORY → see notice below   │
│                                                                  │
│   Telemetry → my_schema.my_events_view (custom view)             │
│     Masking: RECORD, VALUE; stream healthy                       │
│     Or: event table directly → see notice below                  │
│                                                                  │
│ ⚠ If you selected default views or event tables as sources:     │
│   Masking and row access policies cannot be applied to these     │
│   sources. To enforce governance, you have to create your own    │
│   custom views (with masking/row access policies) for this       │
│   source and select those views as the telemetry source.         │
│                                                                  │
│ ⓘ For full governance details, visit                            │
│   Snowsight → Governance & Security → Trust Center              │
└─────────────────────────────────────────────────────────────────┘
```

### 8.6 ACCESS_HISTORY.policies_referenced — Sensitive Query Identification

The `policies_referenced` column in ACCESS_HISTORY is extremely valuable for our app. Its JSON structure records every masking and row access policy enforced during each query:

```json
[
  {
    "columns": [
      {
        "columnId": 68610,
        "columnName": "SSN",
        "policies": [
          {
            "policyName": "governance.policies.ssn_mask",
            "policyId": 68811,
            "policyKind": "MASKING_POLICY"
          }
        ]
      }
    ],
    "objectDomain": "VIEW",
    "objectId": 66564,
    "objectName": "GOVERNANCE.VIEWS.V1",
    "policies": [
      {
        "policyName": "governance.policies.rap1",
        "policyId": 68813,
        "policyKind": "ROW_ACCESS_POLICY"
      }
    ]
  }
]
```

**How we leverage this for QUERY_HISTORY export:**

By joining ACCESS_HISTORY with QUERY_HISTORY on `query_id`, we can identify which queries accessed policy-protected (sensitive) data. This enables:

1. **Targeted QUERY_TEXT enrichment:** When QUERY_TEXT is exported (user selected a custom view without full masking, or the default view, see §8.3), we can annotate the exported log with a `sensitive_data_accessed: true` field for queries that accessed policy-protected data — so Splunk can alert on it.

2. **Compliance audit without extra effort:** The `policies_referenced` data tells us exactly which policies were enforced, on which objects and columns, without needing to manually cross-reference TAG_REFERENCES and POLICY_REFERENCES.

3. **Governance posture intelligence:** When the user selects a custom view as the source (§8.3), `policies_referenced` provides end-to-end governance visibility — the user's view enforces what data leaves Snowflake, and ACCESS_HISTORY records what data was accessed and which policies were enforced.

**SQL patterns for extracting policy enforcement data:**

```sql
-- Identify query_ids that accessed masking-policy-protected columns
SELECT DISTINCT ah.query_id,
    policies.value:"policyName"::VARCHAR AS policy_name,
    columns.value:"columnName"::VARCHAR AS protected_column
FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY ah,
    LATERAL FLATTEN(ah.policies_referenced) obj,
    LATERAL FLATTEN(obj.value:"columns") columns,
    LATERAL FLATTEN(columns.value:"policies") policies
WHERE policies.value:"policyKind"::VARCHAR = 'MASKING_POLICY'
    AND ah.query_start_time >= DATEADD(day, -1, CURRENT_TIMESTAMP());

-- Identify query_ids that hit row access policies
SELECT DISTINCT ah.query_id,
    obj_policy.value:"policyName"::VARCHAR AS policy_name
FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY ah,
    LATERAL FLATTEN(ah.policies_referenced) obj,
    LATERAL FLATTEN(obj.value:"policies") obj_policy
WHERE obj_policy.value:"policyKind"::VARCHAR = 'ROW_ACCESS_POLICY'
    AND ah.query_start_time >= DATEADD(day, -1, CURRENT_TIMESTAMP());
```

**Important latency consideration:** ACCESS_HISTORY has up to **3-hour latency**, while QUERY_HISTORY has up to **45-minute latency**. When our poll-based pipeline reads the governed QUERY_HISTORY view, the corresponding ACCESS_HISTORY records may not yet be available. For the sensitive-query-identification use case, we'd need to either:
- Accept the latency gap (most queries we export won't have ACCESS_HISTORY records yet)
- Use a separate, delayed enrichment pass (post-MVP complexity)
- Keep it simple in MVP: export QUERY_HISTORY from the user-selected source (their view with masking, or default with risk notice), and separately export ACCESS_HISTORY (Security Pack, post-MVP) for compliance audit

### 8.7 Implementation — Querying Governance Posture

**Stored procedure to collect consumer governance posture for the Compliance Panel:**

```python
def collect_governance_posture(session) -> dict:
    """Query consumer's governance metadata for the Governance Compliance panel.

    Uses ACCOUNT_USAGE views and system functions.
    All queries are read-only. No intermediate tables created.
    """

    # 1. Which databases/schemas are monitored by classification?
    monitored = session.sql("""
        SELECT SYSTEM$SHOW_SENSITIVE_DATA_MONITORED_ENTITIES()
    """).collect()[0][0]
    # Returns JSON: [{"name":"DB1","type":"DATABASE","profile_name":"..."},...]

    # 2. Classification profiles active
    profiles = session.sql("""
        SHOW SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE IN ACCOUNT
    """).collect()

    # 3. Semantic categories in use (what types of sensitive data exist)
    semantic_cats = session.sql("""
        SELECT tag_value AS semantic_category, COUNT(*) AS column_count
        FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
        WHERE tag_name = 'SEMANTIC_CATEGORY'
            AND domain = 'COLUMN'
            AND object_deleted IS NULL
        GROUP BY tag_value
        ORDER BY column_count DESC
    """).collect()

    # 4. Privacy categories in use
    privacy_cats = session.sql("""
        SELECT tag_value AS privacy_category, COUNT(*) AS column_count
        FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
        WHERE tag_name = 'PRIVACY_CATEGORY'
            AND domain = 'COLUMN'
            AND object_deleted IS NULL
        GROUP BY tag_value
    """).collect()

    # 5. Active policies by kind
    policies = session.sql("""
        SELECT policy_kind, COUNT(DISTINCT policy_name) AS policy_count,
            COUNT_IF(tag_name IS NOT NULL) AS tag_based_count
        FROM SNOWFLAKE.ACCOUNT_USAGE.POLICY_REFERENCES
        WHERE policy_status = 'ACTIVE'
        GROUP BY policy_kind
    """).collect()

    # 6. Custom classifiers (count from classification profile configs)
    # Extracted from SHOW CLASSIFICATION_PROFILE results if available

    return {
        "monitored_entities": monitored,
        "classification_profiles": len(profiles),
        "semantic_categories": semantic_cats,
        "privacy_categories": privacy_cats,
        "active_policies": policies,
    }
```

### 8.8 Summary — What We Leverage vs. What We Build

| Capability | Snowflake Native (Leverage) | Our App (Build) |
|---|---|---|
| **Data classification** | Automated classification, custom classifiers, classification profiles, Trust Center | Query metadata for Governance Compliance panel; encourage consumers to classify |
| **Column masking** | Dynamic data masking, tag-based masking | When the user selects a **custom view** as the source, they attach masking policies to that view; Snowflake enforces them. We do not create views. |
| **Row filtering** | Row access policies | When the user selects a custom view, they attach RAP to it. We read/stream from the selected source. |
| **Event Table pipeline** | User selects: governed view or event table | We stream from the user's selected source (their view or the event table). If event table selected, we inform that masking cannot be applied. No app-created views. |
| **ACCOUNT_USAGE pipeline** | User selects: custom view or default view | We read from the user's selected source (their view or default ACCOUNT_USAGE view). If default selected, we inform that policies cannot be applied. No app-created views. |
| **Projection control** | Projection policies | Respect consumer projection policies; if a column is blocked, our export adapts |
| **Aggregation privacy** | Aggregation policies | Generally not applicable to our telemetry export use case |
| **Governance metadata** | TAG_REFERENCES, POLICY_REFERENCES, DATA_CLASSIFICATION_LATEST, ACCESS_HISTORY, SYSTEM$SHOW_SENSITIVE_DATA_MONITORED_ENTITIES() | Governance Compliance panel in Streamlit UI |
| **Sensitive query tracking** | ACCESS_HISTORY with `policies_referenced` | Identify queries that accessed protected data; annotate exports; compliance audit |
| **QUERY_TEXT privacy** | User creates a custom view over QUERY_HISTORY and attaches masking (e.g. regex PII scrubbing); selects that view as source. Or selects default view and we inform of risk. | No app-created view or toggle. User selects source; we show risk notice when default ACCOUNT_USAGE view is selected. |
| **No intermediate storage** | — | Serverless tasks read from the user-selected source (their view or default view/table) → transform → export directly to Splunk. No staging/duplication of data. |

---

## Appendix A: Latency Summary for Governance Views

| View | Latency | Retention |
|---|---|---|
| `TAG_REFERENCES` | Up to 120 minutes | As long as object exists |
| `POLICY_REFERENCES` | Up to 120 minutes | As long as policy exists |
| `DATA_CLASSIFICATION_LATEST` | Up to 3 hours | As long as table exists |
| `ACCESS_HISTORY` | Up to 3 hours | 365 days |
| `OBJECT_DEPENDENCIES` | Up to 3 hours | As long as objects exist |
| `MASKING_POLICIES` | Up to 120 minutes | As long as policy exists |
| `ROW_ACCESS_POLICIES` | Up to 120 minutes | As long as policy exists |
| `PROJECTION_POLICIES` | Up to 120 minutes | As long as policy exists |
| `TAGS` | Up to 120 minutes | As long as tag exists |

## Appendix B: Privilege Requirements

| Capability | Required Privilege | Notes |
|---|---|---|
| Read ACCOUNT_USAGE views (TAG_REFERENCES, POLICY_REFERENCES, etc.) | `IMPORTED PRIVILEGES ON SNOWFLAKE DB` | Already required for QUERY_HISTORY access |
| Call SYSTEM$SHOW_SENSITIVE_DATA_MONITORED_ENTITIES() | Role must have access to entities and profiles | May require additional grants in some configurations |
| SHOW CLASSIFICATION_PROFILE | `<profile>!PRIVACY_USER` instance role | Consumer must grant if app needs profile details |
| Read INFORMATION_SCHEMA TAG_REFERENCES function | Role must have access to the tagged object | More granular than ACCOUNT_USAGE; includes inherited tags |
| Consumer creates custom view over ACCOUNT_USAGE / event table | Consumer's schemas and roles | User creates views and attaches masking/RAP; no app-created views |
| Consumer applies masking/row access policy to their views | `APPLY MASKING POLICY` / `APPLY ROW ACCESS POLICY` (or equivalent) | Consumer attaches policies to their own views; they select that view as the app's source |
| Read ACCOUNT_USAGE (default or consumer's view) | `IMPORTED PRIVILEGES ON SNOWFLAKE DB` | We read from the user-selected source (default view or their custom view). Same privilege as direct ACCOUNT_USAGE access. |
| Read Event Tables / user's governed view | Reference mechanism + consumer grants SELECT on table or view | User selects event table or their governed view; we stream from the selected source. Consumer grants SELECT on the object they chose. |
| Create stream on user's view or event table | Consumer grants SELECT; app or consumer creates stream per design | Stream is created on the user-selected source (view or event table). If view, schema compatibility follows that view. |

## Appendix C: Full Semantic Category Reference

### Identifiers (PRIVACY_CATEGORY = IDENTIFIER)

**Global:** BANK_ACCOUNT, EMAIL, IMEI, IP_ADDRESS, NAME, NATIONAL_IDENTIFIER, ORGANIZATION_IDENTIFIER, PAYMENT_CARD, PHONE_NUMBER

**Country-specific subcategories:**
- AU: AU_BUSINESS_NUMBER, AU_COMPANY_NUMBER, AU_DRIVERS_LICENSE, AU_MEDICARE_NUMBER, AU_PASSPORT, AU_PHONE_NUMBER, AU_INDIVIDUAL_TAX_FILE_NUMBER
- CA: CA_BANK_ACCOUNT, CA_DRIVERS_LICENSE, CA_PASSPORT, CA_PHONE_NUMBER, CA_SOCIAL_INSURANCE_NUMBER, CA_PROVINCE_OR_TERRITORY
- EU: EU_DRIVERS_LICENSE, EU_NATIONAL_IDENTIFIER, EU_PASSPORT, EU_PAYMENT_CARD, EU_TAX_IDENTIFIER (added Jan 2026)
- NZ: NZ_BANK_ACCOUNT, NZ_NHI_NUMBER, NZ_PASSPORT, NZ_PHONE_NUMBER
- SG: SG_UNIQUE_ENTITY_NUMBER, SG_PASSPORT, SG_NRIC, SG_FIN
- UK: UK_PHONE_NUMBER, UK_TAX_IDENTIFIER, UK_NHS
- US: US_BANK_ACCOUNT, US_DRIVERS_LICENSE, US_PASSPORT, US_PHONE_NUMBER, US_SOCIAL_SECURITY_NUMBER, US_TAX_IDENTIFIER

### Quasi-Identifiers (PRIVACY_CATEGORY = QUASI_IDENTIFIER)

**Global:** AGE, COUNTRY, DATE_OF_BIRTH, ETHNICITY, GENDER, LATITUDE, LONGITUDE, MARITAL_STATUS, OCCUPATION, YEAR_OF_BIRTH

**Country-specific:** US_STATE_OR_TERRITORY, CA_PROVINCE_OR_TERRITORY, NZ_REGION, US_CITY, US_POSTAL_CODE, CA_POSTAL_CODE, UK_POSTAL_CODE

### Sensitive (PRIVACY_CATEGORY = SENSITIVE)

**Global:** SALARY
