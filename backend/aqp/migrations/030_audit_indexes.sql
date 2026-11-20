CREATE INDEX audit_actor_time ON audit(actor_id, created_at);
CREATE INDEX audit_action_time ON audit(action, created_at);
CREATE INDEX audit_time ON audit(created_at);
