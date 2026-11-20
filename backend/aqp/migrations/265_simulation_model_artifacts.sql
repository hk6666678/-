CREATE TABLE simulation_model_artifacts (
    model_version TEXT PRIMARY KEY,
    trained_at INTEGER NOT NULL,
    artifact TEXT NOT NULL
);
