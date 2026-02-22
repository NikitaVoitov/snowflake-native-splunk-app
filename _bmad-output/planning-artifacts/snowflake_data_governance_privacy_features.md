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
   - 8.3 ACCOUNT_USAGE Privacy — Custom Governed Views (Pattern C for ALL ACCOUNT_USAGE sources across all packs)
   - 8.4 Event Table Privacy (Pattern C: custom governed view + stream for all event tables)
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

> **DESIGN DECISION: Leverage, Don't Replicate**
>
> This is a foundational design principle for how our native app handles sensitive data. Snowflake's governance policies are enforced at the **platform layer** — below our application code. When our stored procedures read ACCOUNT_USAGE views or consumer objects, masking policies, row access policies, and projection policies are enforced automatically by Snowflake's query engine. For Event Tables, masking policies are blocked directly on event tables — our app uses a **custom governed view** (Pattern C) where masking IS supported (see §8.4). For ACCOUNT_USAGE views (e.g., QUERY_HISTORY), policies cannot be applied to the system views directly — our app creates **custom governed views** over them, enabling consumers to attach masking and row access policies (see §8.3). In both cases, the governed view is the **data contract** between the consumer's Snowflake account and our export pipeline — the consumer controls what data leaves their account using Snowflake's native governance tools.

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
| ACCOUNT_USAGE views | **No** | System-managed, read-only. **Workaround:** Create a user-owned view on top of the ACCOUNT_USAGE view — masking, RAP, and projection policies can be applied to the user-owned view. See §8.3. |
| Event Tables (user-created) | **Partial** | RAP and projection work; masking is **blocked**. **Workaround:** Custom governed view. See §8.4. |
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

### 8.1 Core Design Decision: Leverage, Don't Replicate

> **This is a foundational design decision for sensitive data handling.**

Our app does **not** implement its own data classification or privacy enforcement engine. Snowflake's governance policies are enforced at the **platform layer** — below our application code. For both Event Tables and ACCOUNT_USAGE views, policies cannot be applied to the source objects directly (masking is blocked on event tables; ACCOUNT_USAGE views are system-managed). Our app creates **custom governed views** over **every** data source — Pattern C with streams for Event Tables (see §8.4) and governed views with poll-based reads for all ACCOUNT_USAGE sources across all Monitoring Packs (see §8.3). The consumer attaches masking policies, row access policies, and projection policies to these governed views using Snowflake's native governance tools. All policies are enforced automatically by Snowflake's query engine when our pipelines read from the governed views.

**What this means in practice:**

1. **Encourage** consumers to classify their sensitive data using Snowflake's native capabilities (classification profiles, custom classifiers, Trust Center)
2. **Query** classification and policy metadata to understand what the consumer has protected
3. **Respect** the consumer's governance posture — Snowflake enforces policies automatically on our queries
4. **Honor** the full scope of the consumer's data governance measures in our Streamlit UI

### 8.2 Data Sources and Governance Considerations

#### ACCOUNT_USAGE Views (Performance Pack, Cost Pack, Security Pack)

> **Uniform governed view approach:** Every ACCOUNT_USAGE source is queried through a **custom governed view**, regardless of sensitivity level. This gives every data export point a governance hook — the consumer can attach masking, row access, or projection policies to any source without app changes. For low-risk sources the governed view is a simple pass-through; for high-risk sources the app applies a default masking policy. Since ACCOUNT_USAGE uses a poll-based pipeline (no streams), governed views carry none of the CRITICAL risks of the Event Table pattern (no stream breakage, no SQL restrictions). See §8.3 for full architecture.

| Data Source | Sensitive Data Risk | Governed View Strategy |
|---|---|---|
| `QUERY_HISTORY` | **High** — `QUERY_TEXT` may contain literal PII values | Governed view with **default masking policy on QUERY_TEXT** (REDACT mode). Consumer controls via Streamlit toggle (REDACT/FULL/CUSTOM). See §8.3 |
| `LOGIN_HISTORY` | **Medium** — user names, IP addresses, authentication methods | Governed view with **masking hooks** on CLIENT_IP, REPORTED_CLIENT_TYPE. Consumer attaches policies. See §8.3 |
| `ACCESS_HISTORY` | **Medium** — records who accessed what; `policies_referenced` is highly valuable (see §8.6) | Governed view pass-through. Consumer attaches policies if needed. Object/column names generally safe |
| `TASK_HISTORY` | **Low** — operational metadata, no user data | Governed view pass-through. Consumer governance hook available but typically unused |
| `COMPLETE_TASK_GRAPHS` | **Low** — DAG metadata | Governed view pass-through |
| `LOCK_WAIT_HISTORY` | **Low** — lock contention metadata | Governed view pass-through |
| `WAREHOUSE_METERING_HISTORY` | **Low** — credit consumption data | Governed view pass-through |
| `METERING_HISTORY` | **Low** — service-level credit consumption | Governed view pass-through |
| `COPY_HISTORY` | **Low** — file ingestion metadata | Governed view pass-through |
| `SESSIONS` | **Medium** — session metadata, user names, IP addresses | Governed view with masking hooks. Consumer attaches policies |
| `GRANTS_TO_USERS` / `GRANTS_TO_ROLES` | **Low** — privilege metadata | Governed view pass-through |
| `NETWORK_POLICIES` | **Low** — network rule metadata | Governed view pass-through |

#### Event Tables (Distributed Tracing Pack)

| Data Source | Sensitive Data Risk | Governance Approach |
|---|---|---|
| Event Tables (both default and user-created) | **Variable** — depends on what the application logs | Pattern C: Custom governed view → stream. Consumer attaches RAP + masking policies to the view. Masking is blocked on event tables directly — custom view is the only way to redact values. See §8.4 |
| Span/log attributes (RECORD, RECORD_ATTRIBUTES, VALUE) | **High** — may contain PII, credentials, request payloads | Consumer attaches masking policies to the governed view to redact sensitive fields before export |

### 8.3 ACCOUNT_USAGE Privacy — Custom Governed Views

#### Design Decision: Pattern C Applied to ACCOUNT_USAGE Views

> **DECISION:** For **every** ACCOUNT_USAGE source across all Monitoring Packs, our app creates a **custom governed view** and reads from that view instead of the system view directly. The governed view serves the same role as the Event Table governed view (§8.4) — it is the **governed data contract** between the consumer's Snowflake account and our export pipeline. High-risk sources (e.g., QUERY_HISTORY) get a default masking policy applied by the app. Low-risk sources (e.g., TASK_HISTORY, WAREHOUSE_METERING_HISTORY) get a simple pass-through view that still gives the consumer a governance hook. The consumer controls what data leaves their account using Snowflake's native governance tools (masking policies, row access policies, projection policies) on any governed view — no app changes required.

#### The Problem: QUERY_TEXT

`QUERY_TEXT` in QUERY_HISTORY is the **highest-risk field** because it may contain literal sensitive values embedded in SQL:

```sql
-- This query text would appear in QUERY_HISTORY:
SELECT * FROM customers WHERE email = 'jane.doe@example.com' AND ssn = '123-45-6789';
```

**Why a custom governed view solves this:**
- We **cannot** apply masking policies to `ACCOUNT_USAGE.QUERY_HISTORY` directly (system-managed view)
- The consumer cannot apply masking policies to it either
- But we **can** create a user-owned view on top of QUERY_HISTORY, and masking policies **work** on user-created views
- This is the same insight that drives Pattern C for Event Tables — when policies are blocked on the source object, a custom view is the governed intermediary

#### Architecture: Custom Governed View → Poll-Based Pipeline → Splunk

```
SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
    ↓
app_schema.governed_query_history  (custom view + default masking policy on QUERY_TEXT)
    ↓
Poll-based pipeline (watermark) → Transform → HEC → Splunk
```

**Key architectural difference from Event Table Pattern C:** QUERY_HISTORY uses a **poll-based pipeline** (watermark), not a stream-based pipeline. This eliminates all the CRITICAL risks of the Event Table view pattern:

| Risk (from Event Table Pattern C) | Applies to QUERY_HISTORY? | Why |
|---|:---:|---|
| `CREATE OR REPLACE VIEW` breaks streams | **No** | No streams involved — poll-based pipeline |
| View must use simple SQL only (no GROUP BY, DISTINCT, UDFs) | **No** | No stream on the view — no SQL restrictions |
| First stream creation locks underlying table | **No** | No streams to create |
| Triggered task false positives | **No** | Scheduled task, not stream-triggered |
| Secure view staleness risk | **No** | No stream staleness concept |

This makes the governed view pattern for ACCOUNT_USAGE strictly **less risky** than for Event Tables.

#### Pipeline Setup

```sql
-- 1. App creates the governed view during setup.
--    ALL QUERY_HISTORY columns are included. Privacy is enforced via masking
--    policies attached to the view, NOT by column exclusion.
CREATE OR REPLACE VIEW app_schema.governed_query_history AS
SELECT
    QUERY_ID, QUERY_TEXT, DATABASE_NAME, SCHEMA_NAME,
    QUERY_TYPE, SESSION_ID, USER_NAME, ROLE_NAME,
    WAREHOUSE_NAME, WAREHOUSE_SIZE, WAREHOUSE_TYPE,
    CLUSTER_NUMBER, QUERY_TAG, EXECUTION_STATUS,
    ERROR_CODE, ERROR_MESSAGE, START_TIME, END_TIME,
    TOTAL_ELAPSED_TIME, BYTES_SCANNED, ROWS_PRODUCED,
    COMPILATION_TIME, EXECUTION_TIME, QUEUED_PROVISIONING_TIME,
    QUEUED_REPAIR_TIME, QUEUED_OVERLOAD_TIME,
    TRANSACTION_BLOCKED_TIME, OUTBOUND_DATA_TRANSFER_CLOUD,
    OUTBOUND_DATA_TRANSFER_REGION, OUTBOUND_DATA_TRANSFER_BYTES,
    INBOUND_DATA_TRANSFER_CLOUD, INBOUND_DATA_TRANSFER_REGION,
    INBOUND_DATA_TRANSFER_BYTES, CREDITS_USED_CLOUD_SERVICES,
    QUERY_ACCELERATION_BYTES_SCANNED,
    QUERY_ACCELERATION_PARTITIONS_SCANNED,
    QUERY_ACCELERATION_UPPER_LIMIT_SCALE_FACTOR
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY;

-- 2. App applies a DEFAULT masking policy on QUERY_TEXT (safe default = REDACT).
--    This policy always masks QUERY_TEXT — equivalent to the old REDACT mode.
--    No role-based conditionals (IS_ROLE_IN_SESSION returns NULL in Native App context).
CREATE OR REPLACE MASKING POLICY app_schema.default_query_text_mask
    AS (val VARCHAR) RETURNS VARCHAR ->
    '***REDACTED***';

ALTER VIEW app_schema.governed_query_history
    ALTER COLUMN QUERY_TEXT SET MASKING POLICY app_schema.default_query_text_mask;

-- 3. Poll-based pipeline reads from the governed view (same watermark logic as before)
--    SELECT * FROM app_schema.governed_query_history
--    WHERE START_TIME > :last_exported_watermark
--    ORDER BY START_TIME
--    LIMIT :batch_size;
```

#### Consumer-Configured Export Modes (Streamlit UI)

The Streamlit UI Settings panel provides a simple toggle for QUERY_TEXT handling. Under the hood, the toggle manages the masking policy on the governed view:

| Mode | What Happens | Default? |
|---|---|---|
| `REDACT` | App's built-in masking policy is active on `QUERY_TEXT`. All queries return `'***REDACTED***'` for this column. All other QUERY_HISTORY columns are exported normally. | **Yes** |
| `FULL` | App removes the masking policy from the governed view. `QUERY_TEXT` flows through as-is. Consumer explicitly acknowledges privacy implications via a confirmation dialog. | No |
| `CUSTOM` | Consumer has applied their own masking policy to the governed view (detected by the app). App shows the consumer's policy name and status. App does not manage the policy — the consumer owns it. | No |

**Implementation of the toggle:**

```python
def set_query_text_mode(session, mode: str):
    """Switch QUERY_TEXT export mode by managing the masking policy on the governed view."""
    view = "app_schema.governed_query_history"
    default_policy = "app_schema.default_query_text_mask"

    if mode == "REDACT":
        # Ensure default masking policy is active (FORCE replaces any existing policy)
        session.sql(f"""
            ALTER VIEW {view}
                ALTER COLUMN QUERY_TEXT SET MASKING POLICY {default_policy} FORCE
        """).collect()

    elif mode == "FULL":
        # Remove any masking policy from QUERY_TEXT
        session.sql(f"""
            ALTER VIEW {view}
                ALTER COLUMN QUERY_TEXT UNSET MASKING POLICY
        """).collect()
    # CUSTOM mode: no action — consumer manages their own policy
```

**CUSTOM mode detection:** The app queries `INFORMATION_SCHEMA.POLICY_REFERENCES` to check if a non-default masking policy is applied to the governed view's `QUERY_TEXT` column. If a consumer-owned policy is detected, the UI shows `CUSTOM` mode with the policy name.

#### Consumer Governance: Beyond the Toggle

The governed view pattern gives consumers **full control** using Snowflake-native governance tools they already know. The Streamlit UI notifies the consumer that their governed views are the place to enforce data governance for observability exports.

**What the consumer can do (independently, using their own DBAs and security teams):**

1. **Replace the default masking policy with a custom one** — e.g., regex-based PII scrubbing that strips emails and SSNs from QUERY_TEXT while preserving query structure:

```sql
-- Consumer creates their own masking policy (in their schema)
CREATE OR REPLACE MASKING POLICY consumer_schema.scrub_query_pii
    AS (val VARCHAR) RETURNS VARCHAR ->
    REGEXP_REPLACE(
        REGEXP_REPLACE(val,
            '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}',
            '***@redacted.com'),
        '\\b\\d{3}-\\d{2}-\\d{4}\\b',
        '***-**-****'
    );

-- Consumer applies it to the governed view (FORCE replaces app's default policy)
ALTER VIEW app_schema.governed_query_history
    ALTER COLUMN QUERY_TEXT SET MASKING POLICY consumer_schema.scrub_query_pii FORCE;
```

2. **Add a row access policy** — e.g., exclude queries from specific users, databases, or with specific tags:

```sql
-- Consumer creates a RAP to exclude queries from service accounts
CREATE OR REPLACE ROW ACCESS POLICY consumer_schema.filter_export_queries
    AS (user_name VARCHAR) RETURNS BOOLEAN ->
    user_name NOT IN ('SVC_ETL_ACCOUNT', 'SVC_INTERNAL_BOT');

ALTER VIEW app_schema.governed_query_history
    ADD ROW ACCESS POLICY consumer_schema.filter_export_queries ON (USER_NAME);
```

3. **Apply projection policies** — block additional columns beyond QUERY_TEXT from appearing in exports.

4. **Apply tag-based masking** — if the consumer tags columns with sensitivity tags, tag-based masking policies are enforced automatically.

#### Blocked Context Functions — Important Consideration

In the Native App Framework, context functions like `IS_ROLE_IN_SESSION()`, `CURRENT_ROLE()`, and `CURRENT_USER()` return NULL in shared content and owner's-rights stored procedures (see §7.2). Masking policies that use role-based conditions will always evaluate the NULL branch.

**Impact:** Standard role-based masking policies won't differentiate users when data flows through our app's pipeline:

```sql
-- THIS EVALUATES NULL FOR IS_ROLE_IN_SESSION IN NATIVE APP CONTEXT
-- → always falls to ELSE branch (masked)
CREATE MASKING POLICY example AS (val VARCHAR) RETURNS VARCHAR ->
    CASE
        WHEN IS_ROLE_IN_SESSION('ADMIN') THEN val  -- NULL → false
        ELSE '***MASKED***'                         -- always hits this
    END;
```

**This is actually the desired behavior for export use cases** — the app always sees the masked data, which is the safe default. Consumers who want QUERY_TEXT exported unmasked should use the `FULL` toggle or create an unconditional pass-through policy.

**Consumer guidance (shown in Streamlit UI):** Masking policies applied to governed views should not rely on `IS_ROLE_IN_SESSION()` or `CURRENT_ROLE()` for the export pipeline — these functions return NULL in the Native App context. Use unconditional masking (regex scrubbing, field removal) or the REDACT/FULL toggle for controlling QUERY_TEXT export.

#### Comparison: Governed View vs. REDACT/FULL Approach

| Dimension | Previous: App-level REDACT/FULL | New: Uniform Governed Views |
|---|---|---|
| **Consumer simplicity (MVP)** | Toggle in UI | Same toggle in UI (REDACT/FULL) for QUERY_TEXT; pass-through for other sources |
| **Architectural consistency** | Different from Event Table pattern | Same Pattern C for all data sources — Event Tables and ACCOUNT_USAGE |
| **Coverage** | Only QUERY_TEXT in QUERY_HISTORY | Every ACCOUNT_USAGE source across all packs has a governance hook |
| **Granularity** | Binary (exclude column or include as-is) | Binary MVP + partial masking, row filtering, projection control for advanced consumers |
| **Design philosophy** | App implements redaction logic | Platform enforces governance — "Leverage, Don't Replicate" |
| **Row-level filtering** | Not possible | Consumer adds RAP to any governed view |
| **Default safety** | REDACT = safe default | Default masking policy on high-risk sources; pass-through with governance hook on low-risk sources |
| **Post-MVP extensibility** | Need to build PATTERN_REDACT in app code | Consumer creates any policy they want on any governed view — no app changes needed |
| **Performance** | Direct ACCOUNT_USAGE query | View-on-view (negligible overhead for poll-based batches) |
| **Upgrade risk** | None | Low — no streams, `CREATE OR REPLACE VIEW` is safe |

#### ACCESS_HISTORY as Complementary Signal

For observability use cases that benefit from knowing what data was accessed without needing the actual query text:
- ACCESS_HISTORY shows **which objects and columns were accessed** without the query text
- The `policies_referenced` column shows which governance policies were enforced (see §8.6)
- Combined with TAG_REFERENCES, gives a complete picture of sensitive data access patterns
- Our Security Pack (post-MVP) will export ACCESS_HISTORY to Splunk via its own governed view, enabling cross-system compliance monitoring

#### Per-Pack Governed View Strategy

Every ACCOUNT_USAGE source flows through a governed view. The app creates these views during pack enablement. For low-risk sources, the view is a simple `SELECT * FROM` pass-through. For high/medium-risk sources, the app applies a default masking policy. In all cases, the consumer can attach additional policies via `ALTER VIEW`.

**Performance Pack (MVP):**

| Source | Governed View | Default Policy | Consumer Hooks |
|---|---|---|---|
| `QUERY_HISTORY` | `app_schema.governed_query_history` | Masking on `QUERY_TEXT` (REDACT mode) | RAP, masking, projection on any column. Streamlit toggle for QUERY_TEXT mode. |
| `TASK_HISTORY` | `app_schema.governed_task_history` | None (pass-through) | Consumer attaches RAP/masking if needed (e.g., filter by database, mask task names) |
| `COMPLETE_TASK_GRAPHS` | `app_schema.governed_complete_task_graphs` | None (pass-through) | Consumer attaches policies if needed |
| `LOCK_WAIT_HISTORY` | `app_schema.governed_lock_wait_history` | None (pass-through) | Consumer attaches policies if needed |

**Security Pack (post-MVP):**

| Source | Governed View | Default Policy | Consumer Hooks |
|---|---|---|---|
| `LOGIN_HISTORY` | `app_schema.governed_login_history` | Masking hooks on `CLIENT_IP`, `REPORTED_CLIENT_TYPE` | RAP (e.g., exclude service account logins), masking on IP addresses |
| `ACCESS_HISTORY` | `app_schema.governed_access_history` | None (pass-through) | Consumer attaches policies if needed. `policies_referenced` column is critical for compliance — see §8.6 |
| `SESSIONS` | `app_schema.governed_sessions` | Masking hooks on `CLIENT_IP` | RAP, masking on session user/IP data |
| `GRANTS_TO_USERS` | `app_schema.governed_grants_to_users` | None (pass-through) | Consumer attaches policies if needed |
| `GRANTS_TO_ROLES` | `app_schema.governed_grants_to_roles` | None (pass-through) | Consumer attaches policies if needed |
| `NETWORK_POLICIES` | `app_schema.governed_network_policies` | None (pass-through) | Consumer attaches policies if needed |

**Cost Pack (post-MVP):**

| Source | Governed View | Default Policy | Consumer Hooks |
|---|---|---|---|
| `METERING_HISTORY` | `app_schema.governed_metering_history` | None (pass-through) | All cost sources are low-risk operational metadata |
| `WAREHOUSE_METERING_HISTORY` | `app_schema.governed_warehouse_metering_history` | None (pass-through) | Consumer attaches policies if needed |
| `PIPE_USAGE_HISTORY` | `app_schema.governed_pipe_usage_history` | None (pass-through) | Consumer attaches policies if needed |
| `SERVERLESS_TASK_HISTORY` | `app_schema.governed_serverless_task_history` | None (pass-through) | Consumer attaches policies if needed |
| Other cost sources | `app_schema.governed_<source_name>` | None (pass-through) | Same pattern |

**Data Pipeline Pack (post-MVP):**

| Source | Governed View | Default Policy | Consumer Hooks |
|---|---|---|---|
| `COPY_HISTORY` | `app_schema.governed_copy_history` | None (pass-through) | Consumer attaches policies if needed |
| `LOAD_HISTORY` | `app_schema.governed_load_history` | None (pass-through) | Consumer attaches policies if needed |

> **Why governed views even for low-risk sources?** Architectural consistency — every data export point has the same governance contract. The consumer never needs to wonder "does this source have a governance hook?" The answer is always yes. The overhead is negligible (view-on-view adds no measurable cost to poll-based batch reads), and the consumer can add policies to ANY source at ANY time without app changes.

#### Pass-Through Governed View Template

For low-risk sources, the governed view is a simple pass-through created during pack enablement:

```sql
-- Template for low-risk ACCOUNT_USAGE sources (pass-through)
CREATE OR REPLACE VIEW app_schema.governed_<source_name> AS
SELECT *
FROM SNOWFLAKE.ACCOUNT_USAGE.<SOURCE_NAME>;

-- Example: TASK_HISTORY
CREATE OR REPLACE VIEW app_schema.governed_task_history AS
SELECT *
FROM SNOWFLAKE.ACCOUNT_USAGE.TASK_HISTORY;
```

The consumer can then attach policies at any time:

```sql
-- Example: Consumer filters out internal service account tasks
ALTER VIEW app_schema.governed_task_history
    ADD ROW ACCESS POLICY consumer_schema.exclude_service_tasks ON (NAME);

-- Example: Consumer masks task error messages that might contain PII
ALTER VIEW app_schema.governed_task_history
    ALTER COLUMN ERROR_MESSAGE SET MASKING POLICY consumer_schema.mask_task_errors;
```

> **Safe to `CREATE OR REPLACE`:** Unlike Event Table governed views (where `CREATE OR REPLACE VIEW` breaks streams — see §8.4), ACCOUNT_USAGE governed views use poll-based pipelines with no streams. `CREATE OR REPLACE VIEW` is safe and can be used freely during app upgrades or schema migrations.

#### Streamlit UI: ACCOUNT_USAGE Configuration

The ACCOUNT_USAGE configuration in our Streamlit UI must:

1. **Show governed view status per source**: For each enabled ACCOUNT_USAGE source in the selected packs, display the governed view name and whether it exists
2. **Show active policies per governed view**: Query `INFORMATION_SCHEMA.POLICY_REFERENCES` to list any masking, RAP, or projection policies the consumer has attached to each governed view
3. **QUERY_TEXT toggle** (Performance Pack): REDACT/FULL/CUSTOM mode selector for the `governed_query_history` view's QUERY_TEXT masking policy (see Consumer-Configured Export Modes above)
4. **Consumer guidance**: Explain that each governed view is a governance hook — the consumer can attach Snowflake-native policies to control exactly what data is exported per source
5. **Recreate governed views**: Provide a "Rebuild Views" action that recreates pass-through governed views if the consumer needs to reset them (safe for ACCOUNT_USAGE — no stream breakage risk)

```
┌─────────────────────────────────────────────────────────────────┐
│ ACCOUNT_USAGE Governance                                         │
│ Your data flows through governed views before export to Splunk   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│ Performance Pack (MVP):                                          │
│   QUERY_HISTORY      → governed_query_history                    │
│     ✓ QUERY_TEXT mode: [REDACT ▾]  (default masking active)     │
│     ⓘ 0 additional consumer policies attached                   │
│                                                                  │
│   TASK_HISTORY        → governed_task_history                    │
│     ⓘ Pass-through (no default policies)                        │
│     ⓘ 0 consumer policies attached                              │
│                                                                  │
│   COMPLETE_TASK_GRAPHS → governed_complete_task_graphs           │
│     ⓘ Pass-through (no default policies)                        │
│     ⓘ 0 consumer policies attached                              │
│                                                                  │
│   LOCK_WAIT_HISTORY   → governed_lock_wait_history               │
│     ⓘ Pass-through (no default policies)                        │
│     ⓘ 0 consumer policies attached                              │
│                                                                  │
│ ⓘ Attach masking or row access policies to any governed view     │
│   to control what data is exported to Splunk.                    │
│   ALTER VIEW app_schema.governed_<source>                        │
│     ADD ROW ACCESS POLICY ...  |  ALTER COLUMN ... SET MASKING   │
│     POLICY ...                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### 8.4 Event Table Privacy

#### Design Decision: Pattern C — Custom Governed View + Stream

> **DECISION:** For both default and user-created event tables, our app creates a **custom view** over the consumer's event table and streams from that view. The custom view is the **governed data contract** between the consumer's Snowflake account and our app — the consumer controls exactly what telemetry data leaves their account using Snowflake's native governance tools.

> **Full research and live test results:** See [Event Table Streams & Governance Research](event_table_streams_governance_research.md)

**Why a custom view (not direct streaming from the event table):**

Live testing confirmed critical governance constraints on event tables:

| Policy Type | Directly on Event Table | On Custom View |
|---|---|---|
| **Masking policies** | **BLOCKED** (`INVALID OPERATION FOR EVENT TABLES`) | **Works** |
| **Row access policy** | Works (user-created only; not default) | **Works** (both default and user-created) |
| **Projection policy** | Works (user-created only; not default) | **Works** |
| **Column transformation/exclusion** | Not possible | **Works** (via SELECT list, `OBJECT_DELETE`, etc.) |
| **Stream creation** | Works (both default and user-created) | **Works** |

Masking policies are **blocked on all event tables** (including user-created ones). The only way to apply value-level redaction (e.g., strip emails from log messages, remove sensitive JSON keys) is through a **custom view**. This makes Pattern C the only architecture that provides full governance for both event table types.

#### Architecture: Custom View → Stream → Task → Splunk

```
Event Table ──→ Custom View (RAP + Masking + Column Filtering) ──→ Stream (APPEND_ONLY) ──→ Task ──→ Splunk
```

**Pipeline setup (same for both default and user-created event tables):**

```sql
-- 1. Custom view with governance: column transformation, policy hooks
--    The view MUST include all columns the pipeline needs (VALUE is required
--    for LOG messages and METRIC values). Privacy is enforced via masking
--    policies attached to the view, NOT by column exclusion.
CREATE OR REPLACE VIEW app_schema.governed_events_export AS
SELECT
    TIMESTAMP,
    START_TIMESTAMP,
    OBSERVED_TIMESTAMP,
    TRACE,
    RECORD_TYPE,
    RECORD,
    RECORD_ATTRIBUTES,
    -- Remove known-sensitive infrastructure keys from RESOURCE_ATTRIBUTES
    OBJECT_DELETE(
      OBJECT_DELETE(RESOURCE_ATTRIBUTES, 'snow.query.id'),
      'snow.compute_pool.node.id'
    ) AS RESOURCE_ATTRIBUTES,
    SCOPE,
    SCOPE_ATTRIBUTES,
    VALUE                 -- REQUIRED: LOG message text and METRIC values
    -- EXEMPLARS excluded (not used by the export pipeline)
FROM reference('consumer_event_table');

-- 2. Consumer attaches governance policies to the view
--    Row access policy: controls which rows are exported
ALTER VIEW app_schema.governed_events_export
    ADD ROW ACCESS POLICY consumer_schema.event_row_filter ON (RESOURCE_ATTRIBUTES);

--    Masking policy on RECORD: redacts sensitive fields in span/log structured data
ALTER VIEW app_schema.governed_events_export
    ALTER COLUMN RECORD SET MASKING POLICY consumer_schema.mask_log_content;

--    Masking policy on VALUE: redacts PII in log message text and metric payloads
ALTER VIEW app_schema.governed_events_export
    ALTER COLUMN VALUE SET MASKING POLICY consumer_schema.mask_value_content;

-- 3. Stream from the governed view
CREATE STREAM IF NOT EXISTS app_schema.event_stream
    ON VIEW app_schema.governed_events_export
    APPEND_ONLY = TRUE;
```

> **Why VALUE is included, not excluded:** The export pipeline reads `VALUE` for two signal types: **LOGs** (log message text → `message` field in HEC events) and **METRICs** (metric measurement → OTLP metric data points). Excluding `VALUE` from the view would break log and metric export. The consumer protects sensitive content in `VALUE` by attaching a **masking policy** to the governed view's `VALUE` column — Snowflake enforces the mask automatically when the stream is consumed.

**Governance enforcement:** When our serverless task reads from the stream, Snowflake enforces all policies attached to the view — RAP filters rows, masking policies redact sensitive values in RECORD, RECORD_ATTRIBUTES, and VALUE, and excluded columns (EXEMPLARS) never reach our code. This is "Leverage, Don't Replicate" in action.

#### Key Limitations and Operational Rules (from research)

> **Critical architectural insight:** The view SQL restrictions below apply **only to the `CREATE VIEW` definition**, not to queries against the stream. Our Snowpark collector code (which filters by `RECORD_TYPE`, extracts VARIANT fields, and projects per-signal columns) runs at **stream query time** with full SQL/Snowpark capability — no restrictions. The governed view itself is intentionally a simple pass-through with minimal transformations.

| Limitation | Severity | Mitigation / How Our Design Handles It |
|---|---|---|
| `CREATE OR REPLACE VIEW` **breaks all streams** on the view (offset lost, unrecoverable) | **CRITICAL** | Use `ALTER VIEW` for all policy changes (add/drop RAP, masking). Never `CREATE OR REPLACE` the view after streams exist. The app's provisioning and **upgrade process** must never recreate the view — schema migrations require explicit stream drop/recreate with documented data gap. Document prominently for consumers. |
| View must use **simple SQL only** — no GROUP BY, DISTINCT, LIMIT, UDFs, correlated subqueries | **MEDIUM** | **Not a constraint for our design.** The governed view is intentionally a simple column pass-through with only `OBJECT_DELETE` (a system scalar function). All heavy processing — `RECORD_TYPE` filtering, VARIANT field extraction (`col["field"]`), per-signal-type projections, and deduplication — happens in the **Snowpark collector procedure at stream query time**, where no SQL restrictions apply. The view handles governance; Snowpark handles data transformation. |
| First stream creation **locks underlying event table** (one-time change tracking setup) | **MEDIUM** | Schedule during low-activity period. One-time cost per event table. Subsequent stream or view operations do not re-lock. |
| Triggered tasks fire on **all** underlying event table changes (not just rows matching a view filter) | **LOW for our design** | Our governed view does **not** use a WHERE filter — it passes all `RECORD_TYPE` values through. The Snowpark collector filters by signal type at query time. Since every event table insert is a legitimate trigger, false positives are minimal. We use serverless triggered tasks, so even genuinely empty runs (no new data) have negligible cost. |
| Staleness window tied to **underlying table** retention (cannot control for default event table) | **MEDIUM** | **User-created ET:** Set `MAX_DATA_EXTENSION_TIME_IN_DAYS = 90` on the event table during setup (up to 90-day staleness window). **Default ET** (`SNOWFLAKE.TELEMETRY.EVENTS`): Cannot alter retention (system-owned). Must consume stream frequently (every 1–5 min via triggered task) and monitor `STALE_AFTER` aggressively. Avoid `CREATE SECURE VIEW` (secure views do not auto-extend retention). |
| Non-deterministic functions in view definition cause unstable results | **LOW** | Our governed view uses only `OBJECT_DELETE` (deterministic). All other transformations (including any that reference session context) happen in Snowpark at stream query time, outside the view definition. |
| `_staging.stream_offset_log` schema must match the **view** schema, not the event table schema | **MEDIUM** | The zero-row INSERT that advances the stream offset (`INSERT INTO ... SELECT * FROM <stream> WHERE 0 = 1`) requires schema compatibility. Since the stream is on the governed view (which may exclude EXEMPLARS and transform RESOURCE_ATTRIBUTES), the offset log table must be `LIKE <governed_view>`, not `LIKE <event_table>`. |

> **Operational best practices:** See [Pattern C Operational Best Practices](event_table_streams_governance_research.md#operational-best-practices-for-pattern-c)

#### Streamlit UI: Event Table Configuration

The Event Table configuration panel in our Streamlit UI must:

1. **Allow** the consumer to select either a user-created event table or the default event table as the telemetry source
2. **Create a custom governed view** over the selected event table — this is our app's standard pipeline, not an optional feature
3. **Guide** the consumer to attach governance policies (RAP, masking) to the custom view if they want to control what data is exported
4. **Show governance status** for the custom view: which policies (RAP, masking) are currently attached
5. **Monitor stream health:** staleness status via `SHOW STREAMS`, warn if stream is approaching stale

#### Span/Log Attribute Sensitivity

Span and log attributes (RECORD, RECORD_ATTRIBUTES, VALUE columns) are OBJECT/VARIANT type and may contain PII logged by the consumer's applications. Since masking policies are **blocked on event tables directly**, the custom view is the only place to apply value-level redaction.

All three high-risk columns are **included** in the governed view because the pipeline needs them:
- **RECORD** (OBJECT) — contains structured span/log fields (name, kind, status, severity_text). Required for span and log export.
- **RECORD_ATTRIBUTES** (OBJECT) — contains user-defined span/log attributes. Required for OTLP attribute mapping.
- **VALUE** (VARIANT) — contains log message text and metric measurement values. Required for LOG export (`message` field) and METRIC export (metric data points).

The consumer protects sensitive content in these columns by attaching **masking policies** to the governed view — not by excluding the columns from the view.

> **Consumer Guidance (shown in Streamlit UI):** If your applications log sensitive data in span attributes, log messages, or metric payloads (e.g., user IDs, email addresses, request payloads), attach masking policies to the governed view's RECORD, RECORD_ATTRIBUTES, and/or VALUE columns to redact those fields before export to Splunk.

Example masking policies on the custom view:
```sql
-- Masking policy to redact sensitive keys in RECORD (structured span/log fields)
CREATE OR REPLACE MASKING POLICY mask_log_content
    AS (val OBJECT) RETURNS OBJECT ->
    CASE
        WHEN IS_ROLE_IN_SESSION('SPLUNK_EXPORT_ROLE') THEN val
        ELSE OBJECT_DELETE(OBJECT_DELETE(val, 'user.email'), 'user.ssn')
    END;

ALTER VIEW app_schema.governed_events_export
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

ALTER VIEW app_schema.governed_events_export
    ALTER COLUMN VALUE SET MASKING POLICY mask_value_content;
```

### 8.5 Governance Compliance Panel

Our Streamlit UI should include a **Governance Compliance** panel that demonstrates our app fully **honors and respects** the consumer's existing data governance, privacy measures, and protection posture. This is NOT a duplicate of the Trust Center dashboard — we do not show raw classification statistics. Instead, we show how our app's behavior aligns with what the consumer has configured.

**Purpose:** Communicate to the consumer that our app is governance-aware and adapts its behavior based on their configured policies. Build trust.

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
│ Governed Export Views:                                            │
│                                                                  │
│   QUERY_HISTORY → governed_query_history                         │
│     QUERY_TEXT mode: [REDACT ▾]                                 │
│     Masking policy: app_schema.default_query_text_mask (active) │
│     Row access policy: none                                     │
│                                                                  │
│   Event Table → governed_events_export                           │
│     Masking policies: 2 active (RECORD, VALUE)                  │
│     Row access policy: consumer_schema.event_row_filter          │
│     Stream: healthy (stale_after: 85 days)                      │
│                                                                  │
│ ⚠ To enforce your data governance on observability exports,      │
│   attach masking and row access policies to the governed views   │
│   listed above. These views are the data contract between your   │
│   Snowflake account and this app's export pipeline.              │
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

1. **Targeted QUERY_TEXT enrichment:** When QUERY_TEXT is exported (FULL or CUSTOM mode on the governed view, see §8.3), we can annotate the exported log with a `sensitive_data_accessed: true` field for queries that accessed policy-protected data — so Splunk can alert on it.

2. **Compliance audit without extra effort:** The `policies_referenced` data tells us exactly which policies were enforced, on which objects and columns, without needing to manually cross-reference TAG_REFERENCES and POLICY_REFERENCES.

3. **Governance posture intelligence:** Combined with the governed view pattern (§8.3), `policies_referenced` provides end-to-end governance visibility — the governed view enforces what data leaves Snowflake, and ACCESS_HISTORY records what data was accessed and which policies were enforced.

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
- Keep it simple in MVP: export QUERY_HISTORY via the governed view (with masking policies enforced by Snowflake), and separately export ACCESS_HISTORY (Security Pack, post-MVP) for compliance audit

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
| **Column masking** | Dynamic data masking, tag-based masking | Applied on custom governed views for both Event Tables (stream reads) and ACCOUNT_USAGE views (poll reads). Consumer attaches masking policies using Snowflake-native tools. |
| **Row filtering** | Row access policies | Applied on custom governed views. Enforced on stream reads (Event Tables) and poll reads (ACCOUNT_USAGE). Consumer controls which rows are exported. |
| **Event Table pipeline** | Pattern C: Custom governed view → stream → task → Splunk | Same architecture for both default and user-created event tables. Consumer controls exported data via policies on the governed view. |
| **ACCOUNT_USAGE pipeline** | Pattern C: Custom governed view → poll-based task → Splunk | App creates governed views over **every** ACCOUNT_USAGE source across all packs. High-risk sources (QUERY_HISTORY) get default masking policies; low-risk sources get pass-through views. Every export point has a governance hook. Consumer attaches policies to any governed view. No stream-based risks (poll-based pipeline — `CREATE OR REPLACE VIEW` is safe). |
| **Projection control** | Projection policies | Respect consumer projection policies; if a column is blocked, our export adapts |
| **Aggregation privacy** | Aggregation policies | Generally not applicable to our telemetry export use case |
| **Governance metadata** | TAG_REFERENCES, POLICY_REFERENCES, DATA_CLASSIFICATION_LATEST, ACCESS_HISTORY, SYSTEM$SHOW_SENSITIVE_DATA_MONITORED_ENTITIES() | Governance Compliance panel in Streamlit UI |
| **Sensitive query tracking** | ACCESS_HISTORY with `policies_referenced` | Identify queries that accessed protected data; annotate exports; compliance audit |
| **QUERY_TEXT privacy** | Custom governed view with default masking policy (safe default). Consumer can apply own masking policies (regex PII scrubbing, etc.) via Snowflake-native governance. | REDACT/FULL toggle in Streamlit UI. CUSTOM mode detected when consumer applies their own policy. No app-level redaction logic — platform enforces governance. |
| **No intermediate storage** | — | Serverless tasks read governed views → transform → export directly to Splunk. No staging/duplication of data. |

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
| Create masking policies (on app's own tables/views) | Automatic — app is owner of its own schemas | App creates default masking policy on governed QUERY_HISTORY view |
| Apply/unset masking policies (on app's own views) | Automatic — app is owner of its own schemas | REDACT/FULL toggle manages masking policy on `governed_query_history` |
| Consumer applies own masking policy to app's governed views | `APPLY MASKING POLICY ON ACCOUNT` (or APPLY on the specific policy) | Consumer's security officer / ACCOUNTADMIN can apply custom policies to governed views using `FORCE` parameter |
| Consumer applies row access policy to app's governed views | `APPLY ROW ACCESS POLICY ON ACCOUNT` (or equivalent) | Consumer controls which rows are exported to Splunk |
| Read ACCOUNT_USAGE via governed views | `IMPORTED PRIVILEGES ON SNOWFLAKE DB` | App creates governed views (`governed_query_history`, `governed_task_history`, etc.) over all ACCOUNT_USAGE sources. Same privilege as direct access — the governed view is a user-owned view-on-view. |
| Read Event Tables (any type) via governed view | Reference mechanism + consumer grants SELECT | Pattern C: App creates custom view over event table; consumer attaches RAP + masking to the view. Stream from the view. |
| Create streams on governed Event Table views | App owns the view | `CREATE STREAM ON VIEW app_schema.governed_events_export APPEND_ONLY = TRUE` |

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
