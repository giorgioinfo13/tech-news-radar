-- OPERATOR OPERATION: run only after explicit approval and Alembic upgrade head.
-- psql -X -v ON_ERROR_STOP=1 -f backend/sql/create_app_role.sql
-- Connection uses an operator service from a private pg_service.conf, not a URL here.
-- One-time setup: refuses to modify a pre-existing role. No password is stored here.
BEGIN;
DO $setup$
BEGIN
    IF to_regclass('tnr.ai_brief_usage') IS NULL THEN
        RAISE EXCEPTION 'Apply Alembic migration 0013 before role setup';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_class WHERE oid='tnr.app_users'::regclass AND relrowsecurity)
       OR NOT EXISTS (SELECT 1 FROM pg_policy WHERE polrelid='tnr.app_users'::regclass
                      AND polname='app_users_insert_reader') THEN
        RAISE EXCEPTION 'Reader-only provisioning requires the migrated RLS policies';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tnr_app') THEN
        RAISE EXCEPTION 'tnr_app already exists: inspect its grants instead of recreating it';
    END IF;
    CREATE ROLE tnr_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
        NOREPLICATION NOBYPASSRLS NOINHERIT;
END
$setup$;
GRANT USAGE ON SCHEMA tnr TO tnr_app;
GRANT SELECT, INSERT ON tnr.app_users TO tnr_app;
GRANT UPDATE (last_seen_at) ON tnr.app_users TO tnr_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON
    tnr.categories, tnr.sources, tnr.articles, tnr.collection_runs,
    tnr.subscriptions, tnr.article_read_states, tnr.reader_invitations TO tnr_app;
GRANT SELECT, INSERT, UPDATE ON tnr.source_proposals TO tnr_app;
GRANT SELECT, UPDATE ON tnr.ai_brief_control TO tnr_app;
GRANT SELECT, INSERT, UPDATE ON tnr.ai_brief_budget TO tnr_app;
GRANT SELECT, INSERT, UPDATE ON tnr.ai_brief_usage TO tnr_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON tnr.ai_brief_jobs TO tnr_app;
GRANT USAGE ON SEQUENCE
    tnr.categories_id_seq, tnr.sources_id_seq,
    tnr.articles_id_seq, tnr.collection_runs_id_seq, tnr.source_proposals_id_seq TO tnr_app;
COMMIT;
-- Set a random password separately with psql's \password tnr_app prompt.
-- No default grants: review each future migration before granting new objects.
