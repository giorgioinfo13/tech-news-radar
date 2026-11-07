-- OPERATOR OPERATION: run only after explicit approval and Alembic upgrade head.
-- psql -X -v ON_ERROR_STOP=1 -f backend/sql/create_app_role.sql
-- Connection uses an operator service from a private pg_service.conf, not a URL here.
-- One-time setup: refuses to modify a pre-existing role. No password is stored here.
BEGIN;
DO $setup$
BEGIN
    IF to_regclass('tnr.app_users') IS NULL THEN
        RAISE EXCEPTION 'Apply Alembic migrations before role setup';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tnr_app') THEN
        RAISE EXCEPTION 'tnr_app already exists: inspect its grants instead of recreating it';
    END IF;
    CREATE ROLE tnr_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
        NOREPLICATION NOBYPASSRLS NOINHERIT;
END
$setup$;
GRANT USAGE ON SCHEMA tnr TO tnr_app;
GRANT SELECT ON tnr.app_users TO tnr_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON
    tnr.categories, tnr.sources, tnr.articles, tnr.collection_runs,
    tnr.subscriptions, tnr.article_read_states TO tnr_app;
GRANT USAGE ON SEQUENCE
    tnr.categories_id_seq, tnr.sources_id_seq,
    tnr.articles_id_seq, tnr.collection_runs_id_seq TO tnr_app;
COMMIT;
-- Set a random password separately with psql's \password tnr_app prompt.
-- No default grants: review each future migration before granting new objects.
