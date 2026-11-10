-- OPERATOR OPERATION: run after migration 0012 during the authorized release.
-- Grants no permission to change identity, role, name or active status.
BEGIN;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policy WHERE polrelid='tnr.app_users'::regclass
                   AND polname='app_users_update_usage' AND polcmd='w') THEN
        RAISE EXCEPTION 'Apply migration 0012 and verify usage RLS first';
    END IF;
END $$;
GRANT UPDATE (last_seen_at) ON tnr.app_users TO tnr_app;
COMMIT;
