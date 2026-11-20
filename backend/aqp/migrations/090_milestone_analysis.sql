ALTER TABLE pass_rules ADD COLUMN category TEXT NOT NULL DEFAULT 'courses';
CREATE TABLE training_requirements(id INTEGER PRIMARY KEY, college TEXT NOT NULL, major TEXT NOT NULL, config TEXT NOT NULL, actor_id INTEGER NOT NULL, created_at INTEGER NOT NULL);
