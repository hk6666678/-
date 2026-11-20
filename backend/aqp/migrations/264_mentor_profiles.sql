CREATE TABLE mentor_profiles (
    mentor_id INTEGER NOT NULL REFERENCES mentor_directory(id),
    effective_on TEXT NOT NULL,
    direction TEXT NOT NULL,
    title TEXT NOT NULL,
    PRIMARY KEY (mentor_id, effective_on)
);
