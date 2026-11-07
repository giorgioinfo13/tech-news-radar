-- OPERATOR OPERATION: separate approval required, after migration 0005.
-- Does not change passwords, ownership, Data API exposure, or existing data.
BEGIN;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM tnr.alembic_version WHERE version_num = '0005')
       OR NOT EXISTS (SELECT 1 FROM pg_class WHERE oid='tnr.app_users'::regclass AND relrowsecurity)
       OR NOT EXISTS (SELECT 1 FROM pg_policy WHERE polrelid='tnr.app_users'::regclass
                      AND polname='app_users_insert_reader') THEN
        RAISE EXCEPTION 'Apply migration 0005 and verify reader-only RLS first';
    END IF;
END $$;
GRANT SELECT, INSERT ON tnr.app_users TO tnr_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON tnr.reader_invitations TO tnr_app;
COMMIT;
