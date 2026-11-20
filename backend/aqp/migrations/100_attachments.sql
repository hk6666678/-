CREATE TABLE attachment_versions (
 id INTEGER PRIMARY KEY,
 milestone_id INTEGER NOT NULL REFERENCES milestone_records(id),
 version INTEGER NOT NULL,
 relative_path TEXT NOT NULL UNIQUE,
 sha256 TEXT NOT NULL,
 original_filename TEXT NOT NULL,
 media_type TEXT NOT NULL,
 size INTEGER NOT NULL,
 covered_student_ids TEXT NOT NULL,
 uploaded_by INTEGER NOT NULL REFERENCES users(id),
 created_at INTEGER NOT NULL,
 UNIQUE(milestone_id,version)
);
