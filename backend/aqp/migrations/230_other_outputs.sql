CREATE TABLE patents_outputs (
 id INTEGER PRIMARY KEY,
 business_key TEXT NOT NULL UNIQUE,
 version INTEGER NOT NULL DEFAULT 1,
 payload TEXT NOT NULL,
 active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE patents_output_versions (
 output_id INTEGER NOT NULL REFERENCES patents_outputs(id),
 version INTEGER NOT NULL,
 payload TEXT NOT NULL,
 source_department TEXT NOT NULL,
 actor_id INTEGER NOT NULL REFERENCES users(id),
 PRIMARY KEY(output_id,version)
);
CREATE TABLE patents_output_previews (
 id TEXT PRIMARY KEY,
 actor_id INTEGER NOT NULL REFERENCES users(id),
 payload TEXT NOT NULL,
 confirmed INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE awards_outputs (
 id INTEGER PRIMARY KEY,
 business_key TEXT NOT NULL UNIQUE,
 version INTEGER NOT NULL DEFAULT 1,
 payload TEXT NOT NULL,
 active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE awards_output_versions (
 output_id INTEGER NOT NULL REFERENCES awards_outputs(id),
 version INTEGER NOT NULL,
 payload TEXT NOT NULL,
 source_department TEXT NOT NULL,
 actor_id INTEGER NOT NULL REFERENCES users(id),
 PRIMARY KEY(output_id,version)
);
CREATE TABLE awards_output_previews (
 id TEXT PRIMARY KEY,
 actor_id INTEGER NOT NULL REFERENCES users(id),
 payload TEXT NOT NULL,
 confirmed INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE conferences_outputs (
 id INTEGER PRIMARY KEY,
 business_key TEXT NOT NULL UNIQUE,
 version INTEGER NOT NULL DEFAULT 1,
 payload TEXT NOT NULL,
 active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE conferences_output_versions (
 output_id INTEGER NOT NULL REFERENCES conferences_outputs(id),
 version INTEGER NOT NULL,
 payload TEXT NOT NULL,
 source_department TEXT NOT NULL,
 actor_id INTEGER NOT NULL REFERENCES users(id),
 PRIMARY KEY(output_id,version)
);
CREATE TABLE conferences_output_previews (
 id TEXT PRIMARY KEY,
 actor_id INTEGER NOT NULL REFERENCES users(id),
 payload TEXT NOT NULL,
 confirmed INTEGER NOT NULL DEFAULT 0
);
