CREATE TABLE research_outputs (
 id INTEGER PRIMARY KEY,
 business_key TEXT NOT NULL UNIQUE,
 version INTEGER NOT NULL DEFAULT 1,
 payload TEXT NOT NULL,
 active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE research_output_versions (
 output_id INTEGER NOT NULL REFERENCES research_outputs(id),
 version INTEGER NOT NULL,
 payload TEXT NOT NULL,
 source_department TEXT NOT NULL,
 actor_id INTEGER NOT NULL REFERENCES users(id),
 PRIMARY KEY(output_id,version)
);
CREATE TABLE research_output_previews (
 id TEXT PRIMARY KEY,
 actor_id INTEGER NOT NULL REFERENCES users(id),
 payload TEXT NOT NULL,
 confirmed INTEGER NOT NULL DEFAULT 0
);
