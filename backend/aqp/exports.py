"""Real Excel reports. Strings are always literal cells, including formula prefixes."""

from collections.abc import Callable
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import Response
from openpyxl import Workbook


def excel_report(data: dict[str, Any], filename: str) -> Response:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "分析与证据"
    ws.append(["字段路径", "值"])

    def emit(key: str, value: Any) -> None:
        if isinstance(value, dict):
            if not value:
                emit(key, "{}")
            for k, v in value.items():
                emit(f"{key}.{k}" if key else str(k), v)
        elif isinstance(value, list):
            if not value:
                emit(key, "[]")
            for i, v in enumerate(value):
                emit(f"{key}[{i}]", v)
        else:
            ws.append([key, value])
            for cell in ws[ws.max_row]:
                if isinstance(cell.value, str):
                    cell.data_type = "s"

    emit("generated_at", datetime.now(UTC).isoformat())
    for key, value in data.items():
        emit(key, value)
    ws.freeze_panes = "B2"
    ws.column_dimensions["A"].width = 65
    ws.column_dimensions["B"].width = 90
    output = BytesIO()
    wb.save(output)
    return Response(
        output.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}.xlsx"',
            "Cache-Control": "no-store",
        },
    )


# Original uploads never inherit report export or uploader privileges.
def register_original_downloads(
    app: FastAPI, path: Path, current: Callable[..., Any]
) -> None:
    import json

    from fastapi import HTTPException, Request
    from openpyxl import load_workbook

    from aqp.authorization import allowed
    from aqp.store import audit, connection

    @app.get("/api/imports/{batch_id}/download")
    def download(batch_id: int, request: Request) -> Response:
        with connection(path) as db:
            actor, _ = current(db, request)
            batch = db.execute(
                "SELECT * FROM import_batches WHERE id=?", (batch_id,)
            ).fetchone()
            if batch is None:
                raise HTTPException(404, "原始文件不存在")

            def deny() -> None:
                audit(db, actor["id"], "import.download", "restricted", "denied")
                db.commit()
                raise HTTPException(403, "原始文件涉及的全体范围或身份权限不足")

            rows = db.execute(
                "SELECT * FROM import_rows WHERE batch_id=?", (batch_id,)
            ).fetchall()
            if not rows:
                deny()
            known = {(r["sheet"], r["row_number"]) for r in rows}
            original = bytes(batch["original_file"])
            wb = load_workbook(BytesIO(original), read_only=True, data_only=False)
            try:
                for ws in wb:
                    if ws.title not in {r["sheet"] for r in rows} and any(
                        v is not None
                        for values in ws.iter_rows(values_only=True)
                        for v in values
                    ):
                        deny()
                    for number, values in enumerate(
                        ws.iter_rows(min_row=3, values_only=True), 3
                    ):
                        if (
                            any(v is not None for v in values)
                            and (ws.title, number) not in known
                        ):
                            deny()
            finally:
                wb.close()
            for row in rows:
                p = json.loads(row["normalized_json"])
                scopes = [(p.get("所属学院", ""), p.get("专业", ""))]
                student = db.execute(
                    "SELECT * FROM students WHERE id=? OR student_number=?",
                    (row["student_id"], p.get("学号", "")),
                ).fetchone()
                if student:
                    scopes.append((student["college"], student["major"]))
                for college, major in scopes:
                    if (
                        not college
                        or not major
                        or not all(
                            allowed(
                                db, actor["id"], batch["category"], op, college, major
                            )
                            for op in ("download", "identity")
                        )
                    ):
                        deny()
            audit(db, actor["id"], "import.download", str(batch_id))
            return Response(
                original,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={
                    "Content-Disposition": f'attachment; filename="import-{batch_id}.xlsx"',
                    "Cache-Control": "no-store",
                },
            )
