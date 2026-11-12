-- OPERATOR OPERATION: review and authorize separately, after migration 0009.
BEGIN;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM tnr.alembic_version WHERE version_num IN ('0009', '0010', '0011', '0012', '0013')) THEN
        RAISE EXCEPTION 'Apply migration 0009 first';
    END IF;
END $$;
GRANT SELECT, UPDATE ON tnr.ai_brief_control TO tnr_app;
GRANT SELECT, INSERT, UPDATE ON tnr.ai_brief_budget TO tnr_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON tnr.ai_brief_jobs TO tnr_app;
COMMIT;
