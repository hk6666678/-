"""Offline, manifest-verified database and evidence bundle maintenance CLI."""

import argparse
import hashlib
import json
import shutil
import sqlite3
import stat
import tempfile
import zipfile
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path, PurePosixPath

from aqp.store import audit


def safe_path(path: Path) -> Path:
    absolute = path.absolute()
    for part in (absolute, *absolute.parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError("Symbolic links and junctions are not allowed")
    return absolute.resolve()


@contextmanager
def staging(parent: Path) -> Iterator[Path]:
    parent = safe_path(parent)
    temporary = Path(tempfile.mkdtemp(prefix=".aqp-maintenance-", dir=parent)).resolve()
    try:
        yield temporary
    finally:
        # Delete only the exact private directory allocated here, never user targets.
        if temporary.parent != parent or not temporary.name.startswith(
            ".aqp-maintenance-"
        ):
            raise ValueError("Unsafe cleanup boundary")
        shutil.rmtree(temporary)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_database(path: Path, files: dict[str, bytes]) -> None:
    with closing(sqlite3.connect(path)) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Database integrity check failed")
        if db.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("Broken database references")
        for table in ("attachment_versions", "paper_versions"):
            if not db.execute(
                "SELECT 1 FROM sqlite_master WHERE name=?", (table,)
            ).fetchone():
                continue
            for name, sha, size in db.execute(
                f"SELECT relative_path,sha256,size FROM {table}"
            ):
                content = files.get("attachments/" + name)
                if content is None or len(content) != size or digest(content) != sha:
                    raise ValueError("Missing or damaged version evidence")


def create(db_path: Path, attachments: Path, archive: Path) -> None:
    db_path, attachments, archive = map(safe_path, (db_path, attachments, archive))
    if not db_path.is_file() or not attachments.is_dir():
        raise ValueError("Database and attachments directory must exist")
    if archive.exists() or attachments == archive or attachments in archive.parents:
        raise ValueError("Archive must be new and outside attachments")
    with staging(archive.parent) as temp:
        snapshot = temp / "aqp.sqlite3"
        with (
            closing(sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)) as source,
            closing(sqlite3.connect(snapshot)) as dest,
        ):
            source.backup(dest)
        files = {"aqp.sqlite3": snapshot.read_bytes()}
        for item in attachments.rglob("*"):
            safe_path(item)
            if item.is_file():
                files["attachments/" + item.relative_to(attachments).as_posix()] = (
                    item.read_bytes()
                )
        check_database(snapshot, files)
        manifest = {
            "format": 1,
            "consistency": "services-stopped",
            "files": {
                name: {"sha256": digest(data), "size": len(data)}
                for name, data in files.items()
            },
        }
        bundle = temp / "bundle.zip"
        with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as output:
            output.writestr("manifest.json", json.dumps(manifest, sort_keys=True))
            for name, data in files.items():
                output.writestr(name, data)
        # Exclusive creation never replaces an operator's existing archive.
        with archive.open("xb") as output:
            output.write(bundle.read_bytes())


def restore(archive: Path, target: Path) -> None:
    archive, target = map(safe_path, (archive, target))
    if target.exists():
        raise ValueError("Restore target must not exist")
    with staging(target.parent) as temp:
        restored = temp / "restored"
        restored.mkdir()
        with zipfile.ZipFile(archive) as bundle:
            names = bundle.namelist()
            if len(names) != len(set(names)):
                raise ValueError("Duplicate archive entries")
            for info in bundle.infolist():
                name = info.filename
                parts = PurePosixPath(name).parts
                if (
                    not parts
                    or name.startswith("/")
                    or "\\" in name
                    or ":" in name
                    or ".." in parts
                    or "." in parts
                    or info.is_dir()
                    or stat.S_ISLNK(info.external_attr >> 16)
                    or (
                        name not in ("manifest.json", "aqp.sqlite3")
                        and not name.startswith("attachments/")
                    )
                ):
                    raise ValueError("Unsafe archive member")
            manifest = json.loads(bundle.read("manifest.json"))
            if manifest.get("format") != 1 or set(names) != {
                "manifest.json",
                *manifest["files"],
            }:
                raise ValueError("Invalid archive manifest")
            files = {}
            for name, expected in manifest["files"].items():
                data = bundle.read(name)
                if digest(data) != expected["sha256"] or len(data) != expected["size"]:
                    raise ValueError("Archive hash mismatch")
                files[name] = data
                destination = restored / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
        check_database(restored / "aqp.sqlite3", files)
        with closing(sqlite3.connect(restored / "aqp.sqlite3")) as db, db:
            db.execute("DELETE FROM sessions")
            # Expired task claims retain their IDs; fencing prevents stale publication.
            if db.execute(
                "SELECT 1 FROM sqlite_master WHERE name='paper_jobs'"
            ).fetchone():
                db.execute(
                    "UPDATE paper_jobs SET state='queued',lease_until=0,token=NULL WHERE state='processing'"
                )
                db.execute(
                    "UPDATE paper_versions SET status='queued' WHERE id IN (SELECT version_id FROM paper_jobs WHERE state='queued')"
                )
            audit(db, None, "maintenance.restore", "database")
        (restored / "attachments").mkdir(exist_ok=True)
        restored.rename(target)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    backup = sub.add_parser("create")
    backup.add_argument("--db", type=Path, required=True)
    backup.add_argument("--attachments", type=Path, required=True)
    backup.add_argument("--archive", type=Path, required=True)
    backup.add_argument(
        "--services-stopped",
        action="store_true",
        required=True,
        help="Confirm API and all workers are stopped until completion",
    )
    recovery = sub.add_parser("restore")
    recovery.add_argument("--archive", type=Path, required=True)
    recovery.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "create":
            create(args.db, args.attachments, args.archive)
        else:
            restore(args.archive, args.target)
    except (
        ValueError,
        OSError,
        sqlite3.Error,
        zipfile.BadZipFile,
        KeyError,
        TypeError,
    ) as error:
        parser.exit(1, f"Maintenance failed: {error}\n")
    print(
        "Verified backup complete"
        if args.command == "create"
        else "Verified restore complete; login again"
    )


if __name__ == "__main__":
    main()
