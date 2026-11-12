-- OPERATOR OPERATION: run after migration 0013 during the authorized release.
-- The automated backend_full release applies this same grant transactionally.
BEGIN;
GRANT SELECT, INSERT, UPDATE ON tnr.ai_brief_usage TO tnr_app;
COMMIT;
