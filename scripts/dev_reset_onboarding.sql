-- Dev/testing reset for Getting Started onboarding state.
-- Run with:
--   snow sql -c dev --filename scripts/dev_reset_onboarding.sql
CALL SPLUNK_OBSERVABILITY_DEV_APP.app_public.reset_onboarding_dev_state();
