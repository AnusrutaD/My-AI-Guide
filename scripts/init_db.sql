-- Runs automatically on first container startup via docker-entrypoint-initdb.d
-- The app's init_db() also calls this, so it's idempotent.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
