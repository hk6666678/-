CREATE TABLE mentor_directory (
 id INTEGER PRIMARY KEY,
 mentor_number TEXT NOT NULL UNIQUE,
 name TEXT NOT NULL,
 college TEXT NOT NULL,
 major TEXT NOT NULL,
 user_id INTEGER REFERENCES users(id),
 version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE research_groups (
 id INTEGER PRIMARY KEY,
 group_number TEXT NOT NULL UNIQUE,
 name TEXT NOT NULL,
 college TEXT NOT NULL,
 major TEXT NOT NULL,
 version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE mentor_group_relations (
 id INTEGER PRIMARY KEY,
 student_id INTEGER NOT NULL REFERENCES students(id),
 mentor_id INTEGER NOT NULL REFERENCES mentor_directory(id),
 group_id INTEGER NOT NULL REFERENCES research_groups(id),
 start_date TEXT NOT NULL,
 end_date TEXT,
 source_department TEXT NOT NULL,
 version INTEGER NOT NULL DEFAULT 1,
 CHECK(end_date IS NULL OR end_date >= start_date)
);
CREATE TABLE mentor_group_history (
 id INTEGER PRIMARY KEY,
 relation_id INTEGER NOT NULL REFERENCES mentor_group_relations(id),
 version INTEGER NOT NULL,
 payload TEXT NOT NULL,
 actor_id INTEGER NOT NULL REFERENCES users(id),
 reason TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(relation_id,version)
);
CREATE TABLE mentor_group_imports (
 id INTEGER PRIMARY KEY,
 actor_id INTEGER NOT NULL REFERENCES users(id),
 kind TEXT NOT NULL,
 source_department TEXT NOT NULL,
 original_file BLOB NOT NULL,
 state TEXT NOT NULL,
 confirmed INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
