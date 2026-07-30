-- Run once, after `createdb creditflow`:
--   psql -U creditflow -d creditflow -f scripts/init_schemas.sql
--
-- Alembic migrations create TABLES inside each schema, but they assume the
-- schema itself already exists (see docs/CONVENTIONS.md: "one schema per
-- service"). This just creates the 11 Postgres-backed service schemas.
-- (api-gateway holds no DB state; scraper-service uses MongoDB instead.)

CREATE SCHEMA IF NOT EXISTS auth;
CREATE SCHEMA IF NOT EXISTS tenant;         -- user-service
CREATE SCHEMA IF NOT EXISTS billing;
CREATE SCHEMA IF NOT EXISTS credits;
CREATE SCHEMA IF NOT EXISTS usage;
CREATE SCHEMA IF NOT EXISTS ai;             -- ai-generation-service
CREATE SCHEMA IF NOT EXISTS content;
CREATE SCHEMA IF NOT EXISTS scheduler;
CREATE SCHEMA IF NOT EXISTS social;         -- social-publishing-service
CREATE SCHEMA IF NOT EXISTS notification;
CREATE SCHEMA IF NOT EXISTS admin;
