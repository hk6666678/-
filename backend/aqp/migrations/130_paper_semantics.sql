CREATE TABLE paper_semantic_runs (
 id INTEGER PRIMARY KEY, version_id INTEGER NOT NULL REFERENCES paper_versions(id),
 actor_id INTEGER NOT NULL REFERENCES users(id), created_at INTEGER NOT NULL,
 status TEXT NOT NULL, model TEXT NOT NULL, model_config_version INTEGER NOT NULL,
 parser_config TEXT NOT NULL, result TEXT NOT NULL
);
