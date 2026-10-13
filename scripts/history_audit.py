"""Audit a repository's whole history before it goes public (M5-M6 issue 24).

Usage:
  uv run python scripts/history_audit.py [--repo PATH] [--identity "Name <email>"]
                                          [--allow FILE]

Scans every commit reachable from any ref: author and committer identities, every commit
message, and every text blob for
  ip       IPv4 literals outside the private, loopback, link-local, multicast and
           documentation ranges
  email    addresses outside GitHub noreply, noreply at anthropic.com, the example domains
           and the reserved top-level domains (.test, .invalid, .example, .localhost)
  home     absolute home folders (/Users/<name>/, /home/<name>/, C:\\Users\\<name>\\) other
           than the placeholder names me, runner, user and example
  secret   anything skipwatch.redact.redact_text would replace (the kind only, never the value)
Prints one line per finding, such as `ip <address> in <path> @ <short sha>`, then every
identity with its count. Exits 0 only when there are no findings and, with --identity,
every identity equals it; 1 otherwise; 2 when the repository or the allow file cannot be read.

--allow FILE names known, non-personal test values (fake secrets in the redaction tests,
public addresses the URL tests use), one per line: `<kind> <value or *> <path glob>`, with
blank lines and `#` comments ignored. Keep that file outside the repository being audited.

The script holds no personal values: everything it reports comes from the scan.
"""

import argparse
import fnmatch
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
        "224.0.0.0/4",
        "1.2.3.4/32",
    )
]
ALLOWED_EMAIL_SUFFIXES = ("@users.noreply.github.com",)
ALLOWED_EMAIL_DOMAINS = {"anthropic.com": {"noreply"}, "github.com": {"noreply"}}
EXAMPLE_DOMAINS = {"example.com", "example.org", "example.net"}
RESERVED_TLDS = {"test", "invalid", "example", "localhost"}
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
    if address.endswith(ALLOWED_EMAIL_SUFFIXES) or domain.rsplit(".", 1)[-1] in RESERVED_TLDS:
        return True
    if any(domain == d or domain.endswith("." + d) for d in EXAMPLE_DOMAINS):
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


Allowance = tuple[str, str, str]


class AllowFileError(ValueError):
    pass


def read_allow_file(path: Path) -> list[Allowance]:
    allowances: list[Allowance] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 3:
            raise AllowFileError(f"{path}:{number}: expected `<kind> <value or *> <path glob>`")
        kind, value, glob = parts
        allowances.append((kind, value, glob))
    return allowances


def allowed(allowances: list[Allowance], kind: str, value: str, where: str) -> bool:
    return any(
        kind == k and v in ("*", value)
        for k, v, glob in allowances
        if fnmatch.fnmatchcase(where, glob)
    )


def audit(repo: Path, allowances: list[Allowance] | None = None) -> list[str]:
    lines: list[str] = []
    seen: set[tuple[str, str, str]] = set()

    def report(kind: str, value: str, where: str, commit: str) -> None:
        if allowed(allowances or [], kind, value, where):
            return
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
    parser.add_argument("--allow", help="file of known test values to skip (see above)")
    args = parser.parse_args()
    repo = Path(args.repo)
    try:
        allowances = read_allow_file(Path(args.allow)) if args.allow else []
    except (OSError, AllowFileError) as exc:
        print(f"cannot use the allow file: {exc}", file=sys.stderr)
        return 2
    try:
        findings = audit(repo, allowances)
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
