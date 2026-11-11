"""Durable lease worker. A fencing token prevents an expired worker publishing twice."""

import argparse
import json
import re
import time
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from pypdf import PdfReader

from aqp.attachments import read_version_blob, storage_root
from aqp.store import connection, database_path, migrate


def run_once(path: Path, lease_seconds: int = 60) -> bool:
    token = uuid4().hex
    with connection(path) as db:
        db.execute("BEGIN IMMEDIATE")
        job = db.execute(
            "SELECT version_id FROM paper_jobs WHERE state='queued' OR (state='processing' AND lease_until<?) ORDER BY version_id LIMIT 1",
            (int(time.time()),),
        ).fetchone()
        if not job:
            return False
        version_id = job[0]
        db.execute(
            "UPDATE paper_jobs SET state='processing',lease_until=?,token=? WHERE version_id=?",
            (int(time.time()) + lease_seconds, token, version_id),
        )
        db.execute(
            "UPDATE paper_versions SET status='processing' WHERE id=?", (version_id,)
        )
        row = db.execute(
            "SELECT * FROM paper_versions WHERE id=?", (version_id,)
        ).fetchone()
    failure = None
    result = None
    try:
        content = read_version_blob(storage_root(path), row)
        reader = PdfReader(BytesIO(content), strict=True)
        if reader.is_encrypted:
            failure = "encrypted"
        else:
            pages = [
                {"page": i + 1, "text": p.extract_text() or ""}
                for i, p in enumerate(reader.pages)
            ]
            if not any(str(p["text"]).strip() for p in pages):
                failure = "no_text"
            else:
                sections = []
                references = []
                in_refs = False
                for page in pages:
                    for line in str(page["text"]).splitlines():
                        if re.match(
                            r"^\s*(第[一二三四五六七八九十\d]+章|\d+(?:\.\d+)*\s+|参考文献|References\b)",
                            line,
                            re.IGNORECASE,
                        ):
                            sections.append({"page": page["page"], "text": line})
                        if re.match(
                            r"^\s*(参考文献|References)\s*$", line, re.IGNORECASE
                        ):
                            in_refs = True
                        elif in_refs and line.strip():
                            references.append({"page": page["page"], "text": line})
                result = {
                    "page_count": len(pages),
                    "character_count": sum(len(str(p["text"])) for p in pages),
                    "section_count": len(sections),
                    "reference_count": len(references),
                    "pages": pages,
                    "sections": sections,
                    "references": references,
                    "semantic_features": "未提取",
                    "method": "本地规则识别；参考文献按非空行计数，非语义分析",
                }
    except Exception:  # noqa: BLE001 - parser errors become durable failures
        failure = "damaged_or_unavailable"
    with connection(path) as db:
        db.execute("BEGIN IMMEDIATE")
        updated = db.execute(
            "UPDATE paper_jobs SET state='done',lease_until=0 WHERE version_id=? AND token=? AND state='processing'",
            (version_id, token),
        )
        if updated.rowcount:
            db.execute(
                "UPDATE paper_versions SET status=?,failure_code=?,result=? WHERE id=?",
                (
                    "failed" if failure else "succeeded",
                    failure,
                    json.dumps(result, ensure_ascii=False) if result else None,
                    version_id,
                ),
            )
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--lease-seconds", type=int, default=60)
    args = parser.parse_args()
    if args.lease_seconds < 1:
        parser.error("lease must be positive")
    path = database_path()
    migrate(path)
    while True:
        worked = run_once(path, args.lease_seconds)
        if args.once:
            return
        if not worked:
            time.sleep(1)


if __name__ == "__main__":
    main()
