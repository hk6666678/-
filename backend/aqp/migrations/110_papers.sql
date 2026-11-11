CREATE TABLE paper_versions (
 id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL REFERENCES students(id), version INTEGER NOT NULL,
 title TEXT NOT NULL, level TEXT NOT NULL, discipline TEXT NOT NULL, year TEXT NOT NULL,
 relative_path TEXT NOT NULL UNIQUE, sha256 TEXT NOT NULL, original_filename TEXT NOT NULL,
 size INTEGER NOT NULL, covered_student_ids TEXT NOT NULL, uploaded_by INTEGER REFERENCES users(id), created_at INTEGER NOT NULL,
 status TEXT NOT NULL DEFAULT 'queued', failure_code TEXT, result TEXT, UNIQUE(student_id,version)
);
CREATE TABLE paper_jobs (version_id INTEGER PRIMARY KEY REFERENCES paper_versions(id), state TEXT NOT NULL DEFAULT 'queued', lease_until INTEGER NOT NULL DEFAULT 0, token TEXT);
