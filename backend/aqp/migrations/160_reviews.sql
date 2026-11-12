CREATE TABLE paper_reviews (
 id INTEGER PRIMARY KEY,
 candidate_id INTEGER NOT NULL REFERENCES candidate_results(id),
 version INTEGER NOT NULL,
 decision TEXT NOT NULL CHECK(decision IN ('建议推荐','不建议推荐','待补充材料')),
 comment TEXT NOT NULL,
 mode TEXT NOT NULL CHECK(mode IN ('self','proxy')),
 confirmed_by TEXT NOT NULL,
 basis TEXT NOT NULL,
 recorded_by INTEGER NOT NULL REFERENCES users(id),
 created_at INTEGER NOT NULL,
 request_id TEXT NOT NULL,
 request_body TEXT NOT NULL,
 evidence TEXT NOT NULL,
 UNIQUE(candidate_id,version), UNIQUE(recorded_by,request_id)
);
