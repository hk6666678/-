CREATE TABLE user_student_bindings(user_id INTEGER NOT NULL REFERENCES users(id), student_id INTEGER NOT NULL REFERENCES students(id), PRIMARY KEY(user_id,student_id));
