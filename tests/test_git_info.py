import shutil
import subprocess

import pytest

from src.training.train import git_info

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    git(tmp_path, "init")
    git(tmp_path, "config", "user.email", "t@example.org")
    git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "src").mkdir()
    (tmp_path / "reports").mkdir()
    (tmp_path / "src/a.py").write_text("x = 1\n")
    (tmp_path / "reports/train_run.json").write_text("{}")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-m", "init")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_clean_tree_is_not_dirty(repo):
    info = git_info()
    assert info["git_dirty"] == "False" and len(info["git_commit"]) == 40


def test_outputs_deleted_by_dvc_do_not_count_as_dirty(repo):
    (repo / "reports/train_run.json").unlink()  # what `dvc repro` does before a stage
    (repo / "data").mkdir()
    (repo / "data/new.csv").write_text("a\n")  # untracked generated data
    (repo / "mlflow.db").write_text("")
    assert git_info()["git_dirty"] == "False"


def test_modified_or_new_source_files_do_count(repo):
    (repo / "src/a.py").write_text("x = 2\n")
    assert git_info()["git_dirty"] == "True"
    git(repo, "checkout", "--", "src/a.py")
    (repo / "src/b.py").write_text("y = 1\n")  # untracked source file
    assert git_info()["git_dirty"] == "True"


def test_config_changes_count(repo):
    (repo / "params.yaml").write_text("train: {}\n")
    assert git_info()["git_dirty"] == "True"


def test_not_a_git_repo_reports_unknown_commit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert git_info()["git_commit"] == "unknown"
