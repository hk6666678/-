CREATE TABLE grants (
 user_id INTEGER NOT NULL REFERENCES users(id), category TEXT NOT NULL,
 operation TEXT NOT NULL, college TEXT NOT NULL, major TEXT NOT NULL,
 PRIMARY KEY(user_id, category, operation, college, major)
);
