-- Read-only inspection with an operator connection. Every result must match
-- docs/deployment.md before the service receives the application credential.
SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole,
       rolreplication, rolbypassrls, rolinherit
FROM pg_roles WHERE rolname = 'tnr_app';

-- Must return no rows: NOINHERIT alone does not prevent SET ROLE.
SELECT parent.rolname AS granted_role
FROM pg_auth_members m
JOIN pg_roles parent ON parent.oid = m.roleid
JOIN pg_roles member ON member.oid = m.member
WHERE member.rolname = 'tnr_app';

-- USAGE true, CREATE false. The role must own neither the schema nor its objects.
SELECT has_schema_privilege('tnr_app', 'tnr', 'USAGE') AS schema_usage,
       has_schema_privilege('tnr_app', 'tnr', 'CREATE') AS schema_create,
       pg_get_userbyid(nspowner) AS schema_owner
FROM pg_namespace WHERE nspname = 'tnr';
SELECT c.relname, pg_get_userbyid(c.relowner) AS owner
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'tnr' AND pg_get_userbyid(c.relowner) = 'tnr_app';

-- app_users: SELECT/INSERT with reader-only RLS; data/invitation tables: CRUD.
-- source_proposals: SELECT/INSERT/UPDATE only; DELETE false.
-- ai_brief_budget: SELECT/INSERT/UPDATE only, no DELETE or sequence.
-- ai_brief_usage: SELECT/INSERT/UPDATE only, no DELETE or sequence.
-- ai_brief_control: SELECT/UPDATE only. ai_brief_jobs: CRUD, no sequence.
-- alembic_version: no access. TRUNCATE and REFERENCES always false.
SELECT table_name,
       has_table_privilege('tnr_app', format('tnr.%I', table_name), 'SELECT') AS sel,
       has_table_privilege('tnr_app', format('tnr.%I', table_name), 'INSERT') AS ins,
       has_table_privilege('tnr_app', format('tnr.%I', table_name), 'UPDATE') AS upd,
       has_table_privilege('tnr_app', format('tnr.%I', table_name), 'DELETE') AS del,
       has_table_privilege('tnr_app', format('tnr.%I', table_name), 'TRUNCATE') AS trunc,
       has_table_privilege('tnr_app', format('tnr.%I', table_name), 'REFERENCES') AS refs
FROM information_schema.tables WHERE table_schema = 'tnr' ORDER BY table_name;

-- USAGE true, UPDATE/SELECT false (the runtime cannot reset a sequence).
SELECT c.relname,
       has_sequence_privilege('tnr_app', c.oid, 'USAGE') AS usage,
       has_sequence_privilege('tnr_app', c.oid, 'UPDATE') AS upd,
       has_sequence_privilege('tnr_app', c.oid, 'SELECT') AS sel
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'tnr' AND c.relkind = 'S';

-- All false. These roles must not reach tnr via PostgREST/Data API.
SELECT rolname, has_schema_privilege(rolname, 'tnr', 'USAGE') AS schema_usage
FROM pg_roles WHERE rolname IN ('anon', 'authenticated', 'service_role');
SELECT r.rolname, c.relname
FROM pg_roles r CROSS JOIN pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE r.rolname IN ('anon', 'authenticated', 'service_role') AND n.nspname = 'tnr'
  AND c.relkind IN ('r', 'p')
  AND has_table_privilege(r.rolname, c.oid, 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER');
-- The last query must return no rows. Check Data API exposed schemas separately.

-- Only last_seen_at may be updated. All identity/access columns must return false.
SELECT column_name,
       has_column_privilege('tnr_app', 'tnr.app_users', column_name, 'UPDATE') AS upd
FROM information_schema.columns
WHERE table_schema = 'tnr' AND table_name = 'app_users';

-- Three policies and relrowsecurity=true are required for provisioning and usage.
SELECT relrowsecurity FROM pg_class WHERE oid='tnr.app_users'::regclass;
SELECT policyname, cmd, qual, with_check FROM pg_policies
WHERE schemaname='tnr' AND tablename='app_users';
