import json
from pathlib import Path

from aqp.authorization import student_allowed
from aqp.store import connection, migrate


def test_explicit_mentor_intersection(tmp_path: Path) -> None:
    path = tmp_path / "boundary.sqlite3"
    migrate(path)
    with connection(path) as db:
        db.execute(
            "INSERT INTO users(id,username,password_hash,roles,created_at) VALUES (1,'synthetic','unused',?,0)",
            (json.dumps(["mentor", "school_analyst"]),),
        )
        db.execute(
            "INSERT INTO students(id,research_id,student_number,name,college,major,level,entry_year,payload) VALUES (1,'SYN-1','SYN-1','Synthetic','Example','Math','Master',2026,'{}')"
        )
        assert not student_allowed(db, 1, None)
        assert not student_allowed(db, 1, 1)
        db.execute("INSERT INTO user_student_bindings VALUES (1,1)")
        assert student_allowed(db, 1, 1)
        assert not student_allowed(db, 1, 2)
        db.execute("DELETE FROM user_student_bindings")
        assert not student_allowed(db, 1, 1)
        db.execute(
            "UPDATE users SET roles=? WHERE id=1", (json.dumps(["school_analyst"]),)
        )
        assert student_allowed(db, 1, 1)
