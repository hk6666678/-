CREATE TABLE external_assessments (
 id INTEGER PRIMARY KEY, category TEXT NOT NULL, paper_version_id INTEGER NOT NULL REFERENCES paper_versions(id),
 batch TEXT NOT NULL, anonymous_code TEXT NOT NULL, template_version TEXT NOT NULL,
 scores TEXT NOT NULL, comment TEXT NOT NULL, source TEXT NOT NULL, recorded_by INTEGER NOT NULL REFERENCES users(id),
 UNIQUE(category,paper_version_id,batch,anonymous_code)
);
