"""Extend a completed trial_scale manifest using public loopback HTTP APIs."""

import argparse
import json
import shutil
import sqlite3
import subprocess
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import httpx
from openpyxl import Workbook, load_workbook
from trial_restore import serving
from trial_scale import COLLEGE, MAJOR, PASSWORD, checked, grant, login


def run(manifest, output):
    # Snapshot a stopped baseline into a new isolated directory; reruns never mutate it.
    baseline = json.loads(manifest.read_text(encoding="utf-8"))
    assert baseline["synthetic"] and baseline["server_stopped"]
    output.mkdir(parents=True, exist_ok=False)
    with (
        sqlite3.connect(baseline["database"]) as source_db,
        sqlite3.connect(output / "aqp.sqlite3") as target_db,
    ):
        source_db.backup(target_db)
    shutil.copytree(baseline["attachments"], output / "attachments")
    baseline.update(
        database=str(output / "aqp.sqlite3"), attachments=str(output / "attachments")
    )
    manifest = output / "report.json"
    manifest.write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    source = json.loads(manifest.read_text(encoding="utf-8"))
    assert source["synthetic"] and source["server_stopped"]
    report = {
        "synthetic": True,
        "source_manifest": str(manifest),
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "checks": [],
        "status": "running",
    }
    try:
        with (
            serving(Path(source["database"])) as url,
            httpx.Client(base_url=url, timeout=300, trust_env=False) as client,
        ):
            headers = login(client, source["synthetic_account"])
            original = checked(client.get("/api/access/grants"))
            categories = [
                "basic",
                "research_papers",
                "patents",
                "awards",
                "conferences",
                "mentor_groups",
                "talent_evaluation",
                "blind_reviews",
                "defenses",
            ]
            grants = original + [
                {"category": cat, "operation": op, "college": college, "major": MAJOR}
                for college in [COLLEGE, "合成第二学院"]
                for cat in categories
                for op in [
                    "maintain",
                    "view",
                    "identity",
                    "analyze",
                    "export",
                    "activate_evaluation",
                ]
            ]
            # Preserve existing grants without introducing duplicate scope/operation rows.
            grants = list({tuple(sorted(g.items())): g for g in grants}.values())
            grant(client, headers, checked(client.get("/api/me"))["user"], grants)
            students = checked(client.get("/api/students?limit=200"))["items"]
            student = students[0]
            # A second real student is imported through the baseline template.
            book = load_workbook(BytesIO(client.get("/api/templates/basic").content))
            sheet = book.active
            columns = [cell.value for cell in sheet[2]]
            if sheet.max_row > 2:
                sheet.delete_rows(3, sheet.max_row - 2)
            values = {
                "学号": "SYN-FULL10-B",
                "姓名": "合成第二院学生",
                "所属学院": "合成第二学院",
                "专业": MAJOR,
                "培养层次": "硕士",
                "入学年份": 2025,
            }
            sheet.append([values.get(column, "") for column in columns])
            stream = BytesIO()
            book.save(stream)
            batch = checked(
                client.post(
                    "/api/imports/basic/preview",
                    headers=headers,
                    data={"source_department": "合成全域验收"},
                    files={"file": ("b.xlsx", stream.getvalue())},
                )
            )
            checked(client.post(f"/api/imports/{batch['id']}/confirm", headers=headers))
            second = next(
                item
                for item in checked(
                    client.get(
                        f"/api/students?limit=200&offset={source['observed_counts']['students']}"
                    )
                )["items"]
                if item.get("student_number") == "SYN-FULL10-B"
            )
            report["second_student_id"] = second["id"]
            # Real workbook preview/confirmation for both independent assessment categories.
            book = Workbook()
            columns = [
                "category",
                "paper_version_id",
                "batch",
                "anonymous_code",
                "template_version",
                "scores",
                "comment",
                "source",
            ]
            book.active.append(columns)
            for category in ["blind_reviews", "defenses"]:
                book.active.append(
                    [
                        category,
                        source["paper_ids"][0],
                        "SYN-FULL10",
                        "SYN-R1",
                        "simulation-v1",
                        '{"quality":85}',
                        "合成意见",
                        "合成全域验收",
                    ]
                )
            stream = BytesIO()
            book.save(stream)
            batch = checked(
                client.post(
                    "/api/external-assessments/import/preview",
                    headers=headers,
                    files={"file": ("assessments.xlsx", stream.getvalue())},
                )
            )
            assert batch["errors"] == [], batch
            checked(
                client.post(
                    f"/api/external-assessments/import/{batch['id']}/confirm",
                    headers=headers,
                )
            )
            assessments = checked(client.get("/api/external-assessments"))
            assert assessments["count"] == 2, assessments
            report["checks"].append({"external_assessments": assessments["count"]})
            ids = {}
            for route, extra in [
                ("research-outputs", []),
                ("patents", ["发明", "2026-01-01"]),
                ("awards", ["校级", "2026"]),
                ("conferences", ["口头报告", "2026-01-01"]),
            ]:
                book = load_workbook(
                    BytesIO(client.get(f"/api/{route}/template").content)
                )
                book.active.append(
                    [
                        f"SYN-FULL10-{route}",
                        f"合成{route}",
                        student["student_number"],
                        student["name"],
                        1,
                        "第一作者",
                        COLLEGE,
                        MAJOR,
                        *extra,
                    ]
                )
                stream = BytesIO()
                book.save(stream)
                batch = checked(
                    client.post(
                        f"/api/{route}/preview",
                        headers=headers,
                        data={"source_department": "合成全域验收"},
                        files={"file": ("synthetic.xlsx", stream.getvalue())},
                    )
                )
                checked(
                    client.post(
                        f"/api/{route}/previews/{batch['id']}/confirm",
                        headers=headers,
                        json={"accept_changes": False},
                    )
                )
                rows = checked(client.get(f"/api/{route}"))
                assert rows["distinct_outputs"] == 1
                ids[route] = rows["items"][0]["id"]
                report["checks"].append({"output": route, "id": ids[route]})
            checked(
                client.post(
                    f"/api/research-outputs/{ids['research-outputs']}/citations",
                    headers=headers,
                    json={
                        "date": "2026-01-02",
                        "count": 7,
                        "source_department": "合成全域验收",
                    },
                )
            )
            rule = checked(
                client.post(
                    "/api/evaluation-rules",
                    headers=headers,
                    json={
                        "name": "full10 simulation",
                        "college": COLLEGE,
                        "major": MAJOR,
                        "mode": "simulation",
                        "expected_version": 0,
                        "metrics": [
                            {
                                "feature": "patent_count",
                                "weight": 1,
                                "minimum": 0,
                                "maximum": 10,
                            }
                        ],
                    },
                )
            )
            checked(
                client.post(
                    f"/api/evaluation-rules/{rule['id']}/activate",
                    headers=headers,
                    json={
                        "expected_version": 1,
                        "confirmed_by": "synthetic",
                        "basis": "simulation only",
                        "acknowledge_simulation": True,
                    },
                )
            )
            snapshot = checked(
                client.post(
                    "/api/evaluation-snapshots",
                    headers=headers,
                    json={"student_id": student["id"], "rule_id": rule["id"]},
                )
            )
            assert snapshot["total"] == 10, snapshot
            report["snapshot_id"] = snapshot["id"]
            directories = [
                checked(
                    client.post(
                        f"/api/mentor-groups/directory/{kind}",
                        headers=headers,
                        json={
                            "number": "SYN-FULL10",
                            "name": "合成",
                            "college": COLLEGE,
                            "major": MAJOR,
                        },
                    )
                )["id"]
                for kind in ["mentors", "groups"]
            ]
            relation = checked(
                client.post(
                    "/api/mentor-groups/relations",
                    headers=headers,
                    json={
                        "student_id": student["id"],
                        "mentor_id": directories[0],
                        "group_id": directories[1],
                        "start_date": "2025-01-01",
                        "end_date": None,
                        "source_department": "合成全域验收",
                        "reason": "simulation only",
                    },
                )
            )
            report["relation_id"] = relation["id"]
            for path in [
                f"/api/reports/students/{student['id']}",
                f"/api/reports/colleges?college={COLLEGE}&major={MAJOR}",
                f"/api/reports/mentor-groups?as_of=2026-11-13&mentor_id={directories[0]}",
            ]:
                result = checked(client.get(path))
                if path.startswith("/api/reports/students/"):
                    assert result["sections"]["evaluation"]["total"] == 10, result
                    for category in [
                        "research_papers",
                        "patents",
                        "awards",
                        "conferences",
                    ]:
                        assert result["sections"][category]["count"] == 1, result
                if path.startswith("/api/reports/colleges"):
                    assert (
                        result["sections"]["mentor_groups"]["active_relations"] == 1
                    ), result
                report["checks"].append(
                    {
                        "report": path,
                        "export_status": client.get(
                            path.replace("?", "/export?", 1)
                            if "?" in path
                            else path + "/export"
                        ).status_code,
                    }
                )
            # Change the scored source to a cross-college shared patent: same business key, two participants.
            book = load_workbook(BytesIO(client.get("/api/patents/template").content))
            for person in [student, second]:
                book.active.append(
                    [
                        "SYN-FULL10-patents",
                        "合成共同专利更正",
                        person["student_number"],
                        person["name"],
                        1 if person == student else 2,
                        "共同参与",
                        COLLEGE if person == student else "合成第二学院",
                        MAJOR,
                        "发明",
                        "2026-01-01",
                    ]
                )
            stream = BytesIO()
            book.save(stream)
            batch = checked(
                client.post(
                    "/api/patents/preview",
                    headers=headers,
                    data={"source_department": "合成更正来源"},
                    files={"file": ("shared.xlsx", stream.getvalue())},
                )
            )
            checked(
                client.post(
                    f"/api/patents/previews/{batch['id']}/confirm",
                    headers=headers,
                    json={"accept_changes": True},
                )
            )
            shared = checked(client.get("/api/patents"))
            assert (
                shared["distinct_outputs"] == 1
                and shared["personal_participations"] == 2
            ), shared
            assert shared["items"][0]["version"] == 2
            old = checked(client.get(f"/api/evaluation-snapshots/{snapshot['id']}"))
            assert old["stale"] is True, old
            report["checks"].append(
                {
                    "shared_patent_records": 1,
                    "participations": 2,
                    "source_version": 2,
                    "old_snapshot_stale": True,
                }
            )
            # Independent mentor with broad data grants still needs explicit student bindings.
            mentor = checked(
                client.post(
                    "/api/users",
                    headers=headers,
                    json={
                        "username": "full10-mentor",
                        "password": PASSWORD,
                        "roles": ["mentor", "platform_admin"],
                        "request_id": str(uuid4()),
                    },
                ),
                201,
            )
            grant(client, headers, mentor, grants)
            binding_url = f"/api/users/{mentor['id']}/student_bindings"
            binding = checked(client.get(binding_url))
            checked(
                client.put(
                    binding_url,
                    headers=headers,
                    json={
                        "expected_version": binding["version"],
                        "request_id": str(uuid4()),
                        "student_bindings": [student["research_id"]],
                    },
                )
            )
            with httpx.Client(
                base_url=url, timeout=300, trust_env=False
            ) as mentor_client:
                login(mentor_client, "full10-mentor")
                assert (
                    checked(mentor_client.get("/api/students?limit=200"))["total"] == 1
                )
                assert (
                    mentor_client.get(
                        f"/api/reports/students/{second['id']}"
                    ).status_code
                    == 403
                )
                binding = checked(client.get(binding_url))
                checked(
                    client.put(
                        binding_url,
                        headers=headers,
                        json={
                            "expected_version": binding["version"],
                            "request_id": str(uuid4()),
                            "student_bindings": [],
                        },
                    )
                )
                assert (
                    checked(mentor_client.get("/api/students?limit=200"))["total"] == 0
                )
                assert (
                    mentor_client.get(
                        f"/api/reports/students/{student['id']}"
                    ).status_code
                    == 403
                )
            report["checks"].append(
                {
                    "mentor_platform_admin_bound_students": 1,
                    "after_unbind": 0,
                    "report_after_unbind": 403,
                }
            )
            # Restrict the same session to A and then B; current authority must apply immediately.
            for college, expected in [
                (COLLEGE, source["observed_counts"]["students"]),
                ("合成第二学院", 1),
            ]:
                scoped = [g for g in grants if g["college"] == college]
                grant(client, headers, checked(client.get("/api/me"))["user"], scoped)
                listing = checked(client.get("/api/students?limit=200"))
                assert listing["total"] == expected, listing
                hidden = second["id"] if college == COLLEGE else student["id"]
                assert client.get(f"/api/reports/students/{hidden}").status_code == 403
                report["checks"].append(
                    {
                        "college": college,
                        "visible_students": expected,
                        "other_student_report": 403,
                    }
                )
            report["restore_grants"] = grants
            report["restore_paths"] = [
                "/api/research-outputs",
                "/api/patents",
                "/api/awards",
                "/api/conferences",
                "/api/external-assessments",
                "/api/mentor-groups/directory/mentors",
                "/api/mentor-groups/directory/groups",
                "/api/mentor-groups/relations",
                f"/api/evaluation-snapshots/{snapshot['id']}",
                f"/api/reports/students/{student['id']}",
                f"/api/reports/colleges?college={COLLEGE}&major={MAJOR}",
                f"/api/reports/mentor-groups?as_of=2026-11-13&mentor_id={directories[0]}",
            ]
            grant(client, headers, checked(client.get("/api/me"))["user"], original)
            assert (
                client.get(f"/api/evaluation-snapshots/{snapshot['id']}").status_code
                == 403
            )
            report["checks"].append({"revoke_snapshot": 403})
        report["status"] = "passed"
    finally:
        report["server_stopped"] = True
        manifest.with_name("full-platform-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.manifest.resolve(), args.output.resolve())
