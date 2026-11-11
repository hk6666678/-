CREATE TABLE users (
 id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
 password_hash TEXT NOT NULL, roles TEXT NOT NULL,
 active INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL
);
CREATE TABLE sessions (
 token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
 csrf TEXT NOT NULL, expires_at INTEGER NOT NULL
);
CREATE TABLE audit (
 id INTEGER PRIMARY KEY, actor_id INTEGER, action TEXT NOT NULL,
 target TEXT NOT NULL, outcome TEXT NOT NULL, created_at INTEGER NOT NULL
);
CREATE TABLE login_attempts (address TEXT NOT NULL, created_at INTEGER NOT NULL);
CREATE INDEX login_attempt_time ON login_attempts(address, created_at);
