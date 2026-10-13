"""scripts/history_audit.py on throwaway repositories (M5-M6 issue 24).

Every flagged value is assembled at run time, so this file never holds a literal the audit
reports and a rewritten history that contains it can still pass the audit.
"""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "history_audit.py"
TARGET = ("Robert Botto", "132159765+robert-botto@users.noreply.github.com")
OTHER = ("Someone Else", "someone" + "@" + "example.com")
GMAIL = "someone" + "@" + "gmail.com"
PUBLIC_IP = ".".join(["8", "8", "4", "4"])


def _git_env(name, email):
    env = dict(os.environ)
    env.update(
        GIT_AUTHOR_NAME=name,
        GIT_AUTHOR_EMAIL=email,
        GIT_COMMITTER_NAME=name,
        GIT_COMMITTER_EMAIL=email,
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
    )
    return env


def _commit(repo, files, message="change", identity=TARGET):
    for rel, text in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    env = _git_env(*identity)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, env=env)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "--no-gpg-sign", "-m", message],
        check=True,
        env=env,
    )


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "repo"
    path.mkdir()
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(path)], check=True, env=_git_env(*TARGET)
    )
    return path


def _audit(repo, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", str(repo), *args],
        capture_output=True,
        text=True,
        timeout=120,
    )


def _identity(name_email):
    return f"{name_email[0]} <{name_email[1]}>"


def test_clean_history_with_one_identity_passes(repo):
    _commit(repo, {"README.md": "Docs live at https://example.com.\n"})
    r = _audit(repo, "--identity", _identity(TARGET))
    assert r.returncode == 0, r.stdout + r.stderr
    assert _identity(TARGET) in r.stdout


def test_public_ip_and_personal_email_are_flagged(repo):
    _commit(repo, {"notes.txt": f"server {PUBLIC_IP}\nmail {GMAIL}\n"})
    _commit(repo, {"notes.txt": "gone now\n"})  # removed later, still in history
    r = _audit(repo, "--identity", _identity(TARGET))
    assert r.returncode == 1, r.stdout
    lines = r.stdout.splitlines()
    assert any(line.startswith(f"ip {PUBLIC_IP} in notes.txt @ ") for line in lines), r.stdout
    assert any(line.startswith(f"email {GMAIL} in notes.txt @ ") for line in lines), r.stdout


def test_allowlisted_values_are_not_flagged(repo):
    doc_ip = ".".join(["203", "0", "113", "10"])
    text = (
        f"/Users/me/project and /home/runner/work and {doc_ip} and 127.0.0.1\n"
        f"{_identity(TARGET)} and noreply@anthropic.com and test value 1.2.3.4\n"
        "version 2026.8.19 and 0.1.0\n"
    )
    _commit(repo, {"ok.md": text})
    r = _audit(repo)
    assert r.returncode == 0, r.stdout


def test_home_path_and_commit_message_are_flagged(repo):
    home = "/" + "home" + "/" + "alice" + "/"
    _commit(repo, {"run.sh": f"cd {home}code\n"}, message=f"fix for {GMAIL}")
    r = _audit(repo)
    assert r.returncode == 1
    assert any(line.startswith(f"home {home} in run.sh @ ") for line in r.stdout.splitlines())
    assert any(
        line.startswith(f"email {GMAIL} in commit message @ ") for line in r.stdout.splitlines()
    ), r.stdout


def test_windows_home_path_is_flagged(repo):
    home = "C:" + "\\" + "Users" + "\\" + "alice" + "\\"
    _commit(repo, {"win.txt": f"{home}AppData\n"})
    r = _audit(repo)
    assert r.returncode == 1
    assert f"home {home} in win.txt @ " in r.stdout, r.stdout


def test_secrets_found_by_redact_are_flagged(repo):
    token = "ghp_" + "a1B2c3D4e5F6g7H8i9" + "J0k1L2m3N4o5P6q7R8"
    _commit(repo, {"config.py": f'TOKEN = "{token}"\n'})
    r = _audit(repo)
    assert r.returncode == 1
    assert any(line.startswith("secret ") and "config.py" in line for line in r.stdout.splitlines())


def test_two_identities_fail_with_identity_flag(repo):
    _commit(repo, {"a.txt": "a\n"})
    _commit(repo, {"b.txt": "b\n"}, identity=OTHER)
    r = _audit(repo, "--identity", _identity(TARGET))
    assert r.returncode == 1, r.stdout
    assert _identity(OTHER) in r.stdout
    assert _audit(repo).returncode == 0  # identities alone fail only against --identity


def test_every_ref_is_scanned(repo):
    _commit(repo, {"a.txt": "a\n"})
    env = _git_env(*TARGET)
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-b", "side"], check=True, env=env)
    _commit(repo, {"side.txt": f"{GMAIL}\n"})
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "main"], check=True, env=env)
    r = _audit(repo)
    assert r.returncode == 1
    assert f"email {GMAIL} in side.txt" in r.stdout


def test_binary_blobs_are_skipped(repo):
    path = repo / "clip.bin"
    path.write_bytes(b"\x00\x01" + GMAIL.encode() + b"\x00")
    _commit(repo, {})
    assert _audit(repo).returncode == 0


@pytest.mark.parametrize("path", [SCRIPT, Path(__file__)])
def test_script_and_tests_hold_no_personal_values(path):
    spec = importlib.util.spec_from_file_location("history_audit", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    findings = module.scan_text(path.read_text(encoding="utf-8"))
    assert findings == []


def test_reserved_names_are_not_flagged(repo):
    text = (
        "redacted" + "@" + "example.invalid, a" + "@" + "mail.test, db" + "@" + "x.example.com,\n"
        "noreply" + "@" + "github.com, multicast " + ".".join(["224", "0", "0", "1"]) + "\n"
    )
    _commit(repo, {"ok.txt": text})
    r = _audit(repo)
    assert r.returncode == 0, r.stdout


def test_allow_file_suppresses_listed_findings_only(repo, tmp_path):
    _commit(repo, {"tests/t.py": f"{PUBLIC_IP}\n", "src/s.py": f"{PUBLIC_IP}\n"})
    allow = tmp_path / "allow.txt"
    allow.write_text(f"# known test values\n\nip {PUBLIC_IP} tests/*\n", encoding="utf-8")
    r = _audit(repo, "--allow", str(allow))
    assert r.returncode == 1
    assert f"ip {PUBLIC_IP} in src/s.py" in r.stdout
    assert "tests/t.py" not in r.stdout

    allow.write_text(f"ip {PUBLIC_IP} tests/*\nip * src/*\n", encoding="utf-8")
    assert _audit(repo, "--allow", str(allow)).returncode == 0


def test_allow_file_rejects_malformed_lines(repo, tmp_path):
    _commit(repo, {"a.txt": "a\n"})
    allow = tmp_path / "allow.txt"
    allow.write_text("ip only-two\n", encoding="utf-8")
    r = _audit(repo, "--allow", str(allow))
    assert r.returncode == 2
    assert "allow.txt:1" in r.stderr
