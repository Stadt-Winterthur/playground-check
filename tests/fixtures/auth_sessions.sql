-- Test-only session storage, created in each test's random schema.
-- This is not a production migration or an application-schema substitute.
BEGIN;
CREATE TABLE IF NOT EXISTS wgr_sp_auth_session (
    session_id text PRIMARY KEY,
    fid_kontrolleur bigint NOT NULL REFERENCES wgr_sp_kontrolleur(fid) ON DELETE CASCADE,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS wgr_sp_auth_session_account_idx
    ON wgr_sp_auth_session(fid_kontrolleur);
CREATE INDEX IF NOT EXISTS wgr_sp_auth_session_expiry_idx
    ON wgr_sp_auth_session(expires_at);
COMMIT;
