from pathlib import Path

from apexrep.config import REPO_ROOT
from apexrep.migrate import pending_migrations


def write_migrations(directory: Path, names: list[str]) -> None:
    for name in names:
        (directory / name).write_text("select 1;", encoding="utf-8")


def test_pending_migrations_are_sorted(tmp_path: Path) -> None:
    write_migrations(tmp_path, ["0002_b.sql", "0001_a.sql", "0003_c.sql"])
    pending = pending_migrations(tmp_path, applied=set())
    assert [path.name for path in pending] == ["0001_a.sql", "0002_b.sql", "0003_c.sql"]


def test_applied_migrations_are_skipped(tmp_path: Path) -> None:
    write_migrations(tmp_path, ["0001_a.sql", "0002_b.sql"])
    pending = pending_migrations(tmp_path, applied={"0001_a.sql"})
    assert [path.name for path in pending] == ["0002_b.sql"]


def test_non_sql_files_are_ignored(tmp_path: Path) -> None:
    write_migrations(tmp_path, ["0001_a.sql"])
    (tmp_path / "README.md").write_text("notes", encoding="utf-8")
    pending = pending_migrations(tmp_path, applied=set())
    assert [path.name for path in pending] == ["0001_a.sql"]


def test_repo_migrations_directory_has_migrations() -> None:
    assert pending_migrations(REPO_ROOT / "migrations", applied=set())
