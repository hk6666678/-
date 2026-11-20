from pathlib import Path

root = Path(r'D:/AQP-PGS-worktrees/ticket-07')
def edit(rel, replacements):
    path = root / rel
    text = path.read_text(encoding='utf-8')
    for old, new in replacements:
        if old not in text:
            raise SystemExit(f'missing snippet in {rel}: {old[:80]!r}')
        text = text.replace(old, new, 1)
    path.write_text(text, encoding='utf-8', newline='\n')

edit('backend/aqp/authorization.py', [(
'''    "review",
]''',
'''    "review",
    "void",
]''',
)])
edit('backend/aqp/app.py', [(
'''    from aqp.resolutions import register_resolutions

    register_resolutions(app, path, current)
''',
'''    from aqp.resolutions import register_resolutions

    register_resolutions(app, path, current)

    from aqp.records import register_records

    register_records(app, path, current)
''',
)])
edit('backend/aqp/courses.py', [(
'''"SELECT * FROM course_records WHERE state='pending'"''',
'''"SELECT * FROM course_records WHERE state='pending' AND active=1"''',
),(
'''WHERE c.student_id=? AND c.state='linked' ORDER BY c.id''',
'''WHERE c.student_id=? AND c.state='linked' AND c.active=1 ORDER BY c.id''',
)])
edit('backend/aqp/milestones.py', [(
'''"SELECT * FROM milestone_records WHERE student_id IS NULL"''',
'''"SELECT * FROM milestone_records WHERE student_id IS NULL AND active=1"''',
)])
edit('frontend/src/AccessPanel.tsx', [(
'''  review: "人工复核",\n};''',
'''  review: "人工复核",\n  void: "作废",\n};''',
)])
edit('frontend/src/main.tsx', [(
'''import { ResolutionPanel } from "./ResolutionPanel";''',
'''import { RecordPanel } from "./RecordPanel";\nimport { ResolutionPanel } from "./ResolutionPanel";''',
),(
'''          <button onClick={() => setPage("courses")}>课程导入与待关联</button>''',
'''          <button onClick={() => setPage("courses")}>课程导入与待关联</button>\n          <button onClick={() => setPage("records")}>记录更正与作废</button>''',
),(
'''        ) : page === "courses" ? (\n          <CoursePanel csrf={session.csrf_token} />\n        ) : page === "students" ? (''',
'''        ) : page === "courses" ? (\n          <CoursePanel csrf={session.csrf_token} />\n        ) : page === "records" ? (\n          <RecordPanel csrf={session.csrf_token} fetcher={request} />\n        ) : page === "students" ? (''',
)])
edit('frontend/src/style.css', [(
'''button,\ninput {\n  font: inherit;\n}''',
'''button,\ninput,\ntextarea {\n  font: inherit;\n}''',
),(
'''input {\n  display: block;''',
'''input,\ntextarea {\n  display: block;''',
)])
