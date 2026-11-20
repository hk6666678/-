CREATE TABLE research_citations (
 output_id INTEGER NOT NULL REFERENCES research_outputs(id),
 snapshot_date TEXT NOT NULL,
 version INTEGER NOT NULL,
 count INTEGER NOT NULL CHECK(count >= 0),
 source_department TEXT NOT NULL,
 actor_id INTEGER NOT NULL REFERENCES users(id),
 reason TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(output_id,snapshot_date,version)
);
