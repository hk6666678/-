ALTER TABLE users ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE audit ADD COLUMN details TEXT NOT NULL DEFAULT '{}';
CREATE TABLE account_mutations (
 actor_id INTEGER NOT NULL REFERENCES users(id), request_id TEXT NOT NULL,
 fingerprint TEXT NOT NULL, response TEXT NOT NULL,
 PRIMARY KEY(actor_id, request_id)
);
