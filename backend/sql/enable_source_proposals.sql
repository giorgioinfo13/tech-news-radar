-- OPERATOR OPERATION: review and authorize separately, after migration 0006.
BEGIN;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM tnr.alembic_version WHERE version_num IN ('0006', '0007', '0008', '0009')) THEN
        RAISE EXCEPTION 'Apply migration 0006 first';
    END IF;
END $$;
GRANT SELECT, INSERT, UPDATE ON tnr.source_proposals TO tnr_app;
GRANT USAGE ON SEQUENCE tnr.source_proposals_id_seq TO tnr_app;
COMMIT;
