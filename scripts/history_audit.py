"""Audit a repository's whole history before it goes public (M5-M6 issue 24).

Usage:
  uv run python scripts/history_audit.py [--repo PATH] [--identity "Name <email>"]

Scans every commit reachable from any ref: author and committer identities, every commit
message, and every text blob for
  ip       IPv4 literals outside the private, loopback, link-local and documentation ranges
  email    addresses outside GitHub noreply, noreply at anthropic.com and the example domains
  home     absolute home folders (/Users/<name>/, /home/<name>/, C:\\Users\\<name>\\) other
           than the placeholder names me, runner, user and example
  secret   anything skipwatch.redact.redact_text would replace (the kind only, never the value)
Prints one line per finding, such as `ip <address> in <path> @ <short sha>`, then every
identity with its count. Exits 0 only when there are no findings and, with --identity,
every identity equals it; 1 otherwise; 2 when the repository cannot be read.

The script holds no personal values: everything it reports comes from the scan.
"""

import argparse
import ipaddress
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

from skipwatch.redact import redact_text

ALLOWED_NETWORKS = [
    ipaddress.ip_network(net)
    for net in (
        "0.0.0.0/32",
        "127.0.0.0/8",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "169.254.0.0/16",
        "192.0.2.0/24",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "1.2.3.4/32",
    )
]
ALLOWED_EMAIL_SUFFIXES = ("@users.noreply.github.com",)
ALLOWED_EMAIL_DOMAINS = {"anthropic.com": {"noreply"}}
EXAMPLE_DOMAINS = {"example.com", "example.org", "example.net"}
ALLOWED_HOME_NAMES = {"me", "runner", "user", "example"}

IPV4 = re.compile(r"(?<![\w.])(\d{1,3}(?:\.\d{1,3}){3})(?!\.?\d)(?!\w)")
EMAIL = re.compile(
    r"(?<![\w.%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"
)
_NAME = r"([A-Za-z0-9][A-Za-z0-9._-]*)"
HOME_POSIX = re.compile(rf"/(?:Users|home)/{_NAME}/")
HOME_WINDOWS = re.compile(rf"[A-Za-z]:(\\{{1,2}})Users\1{_NAME}\1")
BINARY_PROBE_BYTES = 8000
NO_COMMIT = "-------"


def ip_allowed(text: str) -> bool:
    try:
        address = ipaddress.IPv4Address(text)
    except ValueError:
        return True  # 999.1.2.3 is a version string, not an address
    return any(address in net for net in ALLOWED_NETWORKS)


def email_allowed(address: str) -> bool:
    address = address.lower()
    local, _, domain = address.rpartition("@")
    if address.endswith(ALLOWED_EMAIL_SUFFIXES) or domain in EXAMPLE_DOMAINS:
        return True
    return local in ALLOWED_EMAIL_DOMAINS.get(domain, set())


def scan_text(text: str) -> list[tuple[str, str]]:
    """Every (kind, value) finding in one text, in order, without duplicates."""
    found: list[tuple[str, str]] = []
    for match in IPV4.finditer(text):
        if not ip_allowed(match.group(1)):
            found.append(("ip", match.group(1)))
    for match in EMAIL.finditer(text):
        if not email_allowed(match.group(0)):
            found.append(("email", match.group(0)))
    for pattern, group in ((HOME_POSIX, 1), (HOME_WINDOWS, 2)):
        for match in pattern.finditer(text):
            if match.group(group).lower() not in ALLOWED_HOME_NAMES:
                found.append(("home", match.group(0)))
    _, replacements = redact_text(text)
    found.extend(("secret", item.kind) for item in replacements)
    return list(dict.fromkeys(found))


def git(repo: Path, *args: str, stdin: bytes | None = None) -> bytes:
    return subprocess.run(
        ["git", "-C", str(repo), *args], input=stdin, capture_output=True, check=True
    ).stdout


def blob_commits(repo: Path) -> dict[str, str]:
    """The short sha of the oldest commit that added each blob (merges included)."""
    out = git(repo, "log", "--all", "--reverse", "--raw", "--no-abbrev", "--no-renames", "-m")
    first: dict[str, str] = {}
    commit = NO_COMMIT
    for line in out.decode("utf-8", "replace").splitlines():
        if line.startswith("commit "):
            commit = line.split()[1][:7]
        elif line.startswith(":"):
            new_sha = line.split("\t", 1)[0].split()[3]
            first.setdefault(new_sha, commit)
    return first


def reachable_blobs(repo: Path) -> dict[str, str]:
    """Every object reachable from any ref that has a path, mapped to its first path."""
    paths: dict[str, str] = {}
    for line in git(repo, "rev-list", "--objects", "--all").decode("utf-8", "replace").splitlines():
        sha, _, path = line.partition(" ")
        if path:
            paths.setdefault(sha, path)
    return paths


def read_blobs(repo: Path, shas: list[str]):
    """Yield (sha, bytes) for each blob among `shas` via one `git cat-file --batch`."""
    out = git(repo, "cat-file", "--batch", stdin="".join(f"{s}\n" for s in shas).encode())
    pos = 0
    while pos < len(out):
        header_end = out.index(b"\n", pos)
        sha, kind, size = out[pos:header_end].decode().split()
        start = header_end + 1
        end = start + int(size)
        if kind == "blob":
            yield sha, out[start:end]
        pos = end + 1


def identities(repo: Path) -> Counter[str]:
    out = git(repo, "log", "--all", "--format=%an <%ae>%x00%cn <%ce>")
    counts: Counter[str] = Counter()
    for line in out.decode("utf-8", "replace").splitlines():
        counts.update(line.split("\x00"))
    return counts


def commit_messages(repo: Path):
    out = git(repo, "log", "--all", "--format=%H%x00%B%x01")
    for record in out.decode("utf-8", "replace").split("\x01"):
        sha, _, body = record.strip("\n").partition("\x00")
        if sha:
            yield sha[:7], body


def audit(repo: Path) -> list[str]:
    lines: list[str] = []
    seen: set[tuple[str, str, str]] = set()

    def report(kind: str, value: str, where: str, commit: str) -> None:
        if (kind, value, where) not in seen:
            seen.add((kind, value, where))
            lines.append(f"{kind} {value} in {where} @ {commit}")

    for commit, body in commit_messages(repo):
        for kind, value in scan_text(body):
            report(kind, value, "commit message", commit)
    paths = reachable_blobs(repo)
    commits = blob_commits(repo)
    for sha, data in read_blobs(repo, list(paths)):
        if b"\0" in data[:BINARY_PROBE_BYTES]:
            continue
        for kind, value in scan_text(data.decode("utf-8", "replace")):
            report(kind, value, paths[sha], commits.get(sha, NO_COMMIT))
    return lines


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--identity", help='the only allowed "Name <email>"')
    args = parser.parse_args()
    repo = Path(args.repo)
    try:
        findings = audit(repo)
        people = identities(repo)
    except subprocess.CalledProcessError as exc:
        print(f"cannot read {repo}: {exc.stderr.decode(errors='replace').strip()}", file=sys.stderr)
        return 2
    for line in findings:
        print(line)
    print("identities:")
    for person, count in people.most_common():
        print(f"  {count:6d}  {person}")
    strangers = [p for p in people if args.identity is not None and p != args.identity]
    for person in strangers:
        print(f"UNEXPECTED identity {person}")
    print(f"history audit: {len(findings)} findings, {len(people)} identities")
    return 1 if findings or strangers else 0


if __name__ == "__main__":
    sys.exit(main())
