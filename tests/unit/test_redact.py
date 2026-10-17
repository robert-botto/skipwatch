from pathlib import Path

import pytest
from typer.testing import CliRunner

from skipwatch.cli import app
from skipwatch.redact import redact_text
from skipwatch.workdir import WorkDir

KEY = "sk-proj-FIXTURE0NLY0000000000000000000000000000"


def test_redact_replaces_openai_key():
    out, reps = redact_text(f"OPENAI_API_KEY={KEY}")
    assert KEY not in out and "<OPENAI_API_KEY>" in out
    assert reps[0].kind == "openai" and reps[0].count == 1


def test_redact_report_never_contains_value():
    _, reps = redact_text(KEY)
    assert all(KEY not in r.model_dump_json() for r in reps)


def test_redact_assignment_and_entropy():
    out, _ = redact_text("password: hunter22x and token=Zx9qL2mP7vR4tY8wK3nB6cD1fG5hJ0sAeU")
    assert "hunter22x" not in out and "Zx9qL2mP7vR4tY8wK3nB6cD1fG5hJ0sAeU" not in out


def test_redact_bare_high_entropy_run():
    blob = "Zx9qL2mP7vR4tY8wK3nB6cD1fG5hJ0sAeU"
    out, reps = redact_text(f"value {blob} here")
    assert blob not in out and [r.kind for r in reps] == ["high_entropy"]


def test_redact_leaves_hex_hashes_alone():
    sha = "sha256:" + "a3f1" * 16
    git = "9f2c4e1b7a0d3c5e8f6a1b2c3d4e5f6a7b8c9d0e"
    out, reps = redact_text(f"{sha} {git}")
    assert out == f"{sha} {git}" and reps == []


def test_redact_leaves_real_sha256_and_words_alone():
    import hashlib

    digest = hashlib.sha256(b"skipwatch").hexdigest()
    text = f"sha256:{digest} skipdemo-init-hello-project-ready-and-more-words"
    out, reps = redact_text(text)
    assert out == text and reps == []


def test_redact_counts_per_kind():
    other = "sk-proj-SECOND0NLY000000000000000000000000000"
    _, reps = redact_text(f"{KEY} and {other} and AKIAABCDEFGHIJKLMNOP")
    assert {(r.kind, r.count) for r in reps} == {("openai", 2), ("aws", 1)}


def test_redact_anthropic_before_openai():
    out, reps = redact_text("sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123")
    assert out == "<ANTHROPIC_API_KEY>" and reps[0].kind == "anthropic"


def test_redact_is_idempotent():
    once, _ = redact_text(f"key {KEY}")
    twice, reps = redact_text(once)
    assert once == twice and reps == []


def test_redact_stdin_command():
    r = CliRunner().invoke(app, ["redact", "--stdin"], input=f"use {KEY}\n")
    assert r.exit_code == 0 and "<OPENAI_API_KEY>" in r.stdout and KEY not in r.stdout


def test_redact_without_stdin_flag_is_usage_error():
    r = CliRunner().invoke(app, ["redact"])
    assert r.exit_code == 64


FIXTURE_SETTING = "OPENAI_API_KEY=sk-proj-FIXTURE0NLY0000000000000000000000000000"


def test_redact_exact_fixture_string_by_prefix():
    # The fixture key is low entropy (mostly zeros); only the prefix pattern can catch it.
    out, reps = redact_text(FIXTURE_SETTING)
    assert out == "OPENAI_API_KEY=<OPENAI_API_KEY>"
    assert [(r.kind, r.count) for r in reps] == [("openai", 1)]


# Built by concatenation so no complete token-shaped literal sits in the source.
PROVIDER_CASES = [
    ("openai", "sk-" + "0" * 32, "<OPENAI_API_KEY>"),
    ("openai", "sk-proj-" + "0" * 32, "<OPENAI_API_KEY>"),
    ("anthropic", "sk-ant-" + "api03-" + "0" * 30, "<ANTHROPIC_API_KEY>"),
    ("github", "ghp_" + "A" * 36, "<GITHUB_TOKEN>"),
    ("github", "gho_" + "A" * 36, "<GITHUB_TOKEN>"),
    ("github", "ghs_" + "A" * 36, "<GITHUB_TOKEN>"),
    ("github", "ghu_" + "A" * 36, "<GITHUB_TOKEN>"),
    ("github", "github_pat_" + "A" * 22 + "_" + "B" * 59, "<GITHUB_TOKEN>"),
    ("aws", "AKIA" + "A" * 16, "<AWS_ACCESS_KEY_ID>"),
    ("aws", "ASIA" + "A" * 16, "<AWS_ACCESS_KEY_ID>"),
    ("google", "AIza" + "A" * 35, "<GOOGLE_API_KEY>"),
    ("slack", "xoxb-" + "0" * 12 + "-" + "A" * 24, "<SLACK_TOKEN>"),
    ("slack", "xoxp-" + "0" * 12 + "-" + "A" * 24, "<SLACK_TOKEN>"),
    ("slack", "xoxa-" + "0" * 12 + "-" + "A" * 24, "<SLACK_TOKEN>"),
    ("slack", "xoxr-" + "0" * 12 + "-" + "A" * 24, "<SLACK_TOKEN>"),
    ("stripe", "sk_" + "live_" + "0" * 24, "<STRIPE_KEY>"),
    ("stripe", "rk_" + "live_" + "0" * 24, "<STRIPE_KEY>"),
    ("stripe", "sk_" + "test_" + "0" * 24, "<STRIPE_KEY>"),
    ("huggingface", "hf_" + "A" * 34, "<HF_TOKEN>"),
]


@pytest.mark.parametrize(
    ("kind", "token", "placeholder"),
    PROVIDER_CASES,
    ids=[f"{k}-{t[:4]}" for k, t, _ in PROVIDER_CASES],
)
def test_redact_provider_prefix(kind, token, placeholder):
    out, reps = redact_text(f"export TOKEN_VALUE {token} done")
    assert token not in out and placeholder in out
    assert [r.kind for r in reps] == [kind]


def test_redact_stdin_replaces_invalid_bytes_and_keeps_valid_utf8():
    # Staging files must stay valid UTF-8 for check, so invalid bytes become U+FFFD.
    raw = b"caf\xc3\xa9 \xff\xfe bad bytes " + FIXTURE_SETTING.encode() + b"\r\nend"
    r = CliRunner().invoke(app, ["redact", "--stdin"], input=raw)
    assert r.exit_code == 0
    assert r.stdout_bytes == (
        "caf\u00e9 \ufffd\ufffd bad bytes OPENAI_API_KEY=<OPENAI_API_KEY>\r\nend".encode()
    )
    assert b"replaced 1 openai" in r.stderr_bytes and b"replaced" not in r.stdout_bytes


def test_redact_fixture_key_is_invisible_to_the_entropy_rule():
    from skipwatch.redact import is_secret_like

    key = FIXTURE_SETTING.split("=", 1)[1]
    assert not is_secret_like(key)  # so only the prefix pattern can catch it


def test_redact_stdin_shell_metacharacters_and_heredoc_marker():
    draft = (
        "Run `skipdemo init` then \"quoted\" and 'single' text.\n"
        "echo $(whoami) and ${HOME} and `date`\n"
        "EOF\n"
        "\u00e9t\u00e9 \u65e5\u672c \U0001f600\n"
        f"{FIXTURE_SETTING}\n"
        "EOF"
    )
    r = CliRunner().invoke(app, ["redact", "--stdin"], input=draft.encode())
    assert r.exit_code == 0
    # stdout is the redacted file: byte-exact on every OS. stderr is a human report, so its
    # line endings follow the platform.
    assert (
        r.stdout_bytes == draft.replace(FIXTURE_SETTING, "OPENAI_API_KEY=<OPENAI_API_KEY>").encode()
    )
    assert r.stderr_bytes.decode().replace("\r\n", "\n") == (
        "replaced 1 openai with <OPENAI_API_KEY>\n"
    )


# ---- adversarial review (m1d-review) ----

ZW = "​"
SPLIT_KEY_HEAD = "sk-proj-Ab3dEf6hIj9kLm"
SPLIT_KEY_TAIL = "2nOp5qRs8tUv1wXy4zAb7cDe"


@pytest.mark.parametrize(
    "text",
    [
        'class="risk-assessment-dashboard-container-wrapper-v2"',
        'class="task-list-item-checkbox-disabled-state-wrapper"',
        "Use the disk-usage-analyzer-pro-extension-2024 plugin",
        "mask-image-gradient-transparent-overlay-fallback",
        "the hf_hub_download_and_cache_helper_function_name helper",
    ],
    ids=["risk-css", "task-css", "kebab-name", "mask-css", "hf-substring"],
)
def test_redact_prefix_patterns_need_a_left_boundary(text):
    out, reps = redact_text(text)
    assert out == text and reps == []


@pytest.mark.parametrize(
    "text",
    [
        "token: required for every request",
        "Password: forgotten? Click reset.",
        "The secret: consistency matters",
        'token = os.environ["TOKEN"]',
        "api_key: process.env.OPENAI_API_KEY2",
        "TOKEN=${GITHUB_TOKEN2}",
        "password = getpass()",
        "secret: <YOUR_SECRET_2>",
    ],
    ids=[
        "token-prose",
        "password-prose",
        "secret-prose",
        "os-environ",
        "process-env",
        "shell-var",
        "call",
        "placeholder",
    ],
)
def test_redact_assignment_leaves_prose_and_code_alone(text):
    out, reps = redact_text(text)
    assert out == text and reps == []


@pytest.mark.parametrize(
    ("text", "secret"),
    [
        ("OPENAI_API_KEY=Zx9Lq2Wv8Rt", "Zx9Lq2Wv8Rt"),
        ("client_secret=Zx9Lq2Wv8Rt", "Zx9Lq2Wv8Rt"),
        ("access_token: Zx9Lq2Wv8Rt", "Zx9Lq2Wv8Rt"),
        ('{"api_key": "Zx9Lq2Wv8Rt"}', "Zx9Lq2Wv8Rt"),
        ('password = "hunter22x"', "hunter22x"),
        ("aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "wJalrXUtnFEMI"),
        ("Authorization: Bearer Zx9Lq2Wv8Rt4Yu7Io", "Zx9Lq2Wv8Rt4Yu7Io"),
    ],
    ids=[
        "env-prefixed",
        "client-secret",
        "access-token",
        "json",
        "quoted-password",
        "aws-secret",
        "bearer",
    ],
)
def test_redact_catches_named_and_bearer_secrets(text, secret):
    out, reps = redact_text(text)
    assert secret not in out and reps


@pytest.mark.parametrize(
    "text",
    [
        "/Users/someone/Library/Application_Support/Code/User/globalStorage/ext-v1234/s.json",
        "useCallbackMemoizedSelectorFactoryForUserProfile2",
        "get_user_profile_settings_from_remote_cache_v2_backup",
        "integrity sha512-v2kDEe57lecTulaDIuNTPy3Ry4gLGJ6Z1O3vE1krgXZNrsQ+V1tNDRnU3kxWdVmJ8Yv8q4"
        "Hn2W9C5BG/Z2Q3Ng==",
        'src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk'
        'YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="',
    ],
    ids=["path", "camel", "snake", "sri", "data-uri"],
)
def test_redact_entropy_rule_spares_paths_identifiers_and_integrity(text):
    out, reps = redact_text(text)
    assert out == text and reps == []


def test_redact_zero_width_split_key():
    key = "sk-proj-Ab3dEf6hIj" + ZW + "9kLm2nOp5qRs8tUv1wXy4z"
    out, reps = redact_text(f"use {key} now")
    assert out == "use <OPENAI_API_KEY> now" and [r.kind for r in reps] == ["openai"]


def test_redact_zero_width_in_normal_text_untouched():
    text = "family emoji \U0001f468‍\U0001f469 and word" + ZW + "break"
    assert redact_text(text) == (text, [])


def test_redact_key_split_across_lines():
    out, reps = redact_text(f"OPENAI_API_KEY={SPLIT_KEY_HEAD}\n{SPLIT_KEY_TAIL}\nnext")
    assert SPLIT_KEY_HEAD not in out and SPLIT_KEY_TAIL not in out
    assert out == "OPENAI_API_KEY=<OPENAI_API_KEY>\n\nnext"
    assert [r.kind for r in reps] == ["openai"]


def test_redact_split_lines_leave_ordinary_lines_alone():
    text = "sk-proj-short\nsomething else entirely"
    assert redact_text(text) == (text, [])


def test_redact_db_url_password():
    out, reps = redact_text("DATABASE_URL=postgres://admin:Zx9Lq2Wv8R@db.example.com/app")
    assert out == "DATABASE_URL=postgres://admin:<PASSWORD>@db.example.com/app"
    assert [r.kind for r in reps] == ["url_password"]


def test_redact_private_key_block():
    pem = (
        "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQ\n"
        "-----END OPENSSH PRIVATE KEY-----"
    )
    out, reps = redact_text(f"before\n{pem}\nafter")
    assert out == "before\n<PRIVATE_KEY>\nafter" and [r.kind for r in reps] == ["private_key"]


def test_redact_review_outputs_are_idempotent():
    text = (
        "OPENAI_API_KEY=Zx9Lq2Wv8Rt Bearer Zx9Lq2Wv8Rt4Yu7Io postgres://a:Zx9Lq2Wv8R@h/x "
        f"={SPLIT_KEY_HEAD}\n{SPLIT_KEY_TAIL}"
    )
    once, _ = redact_text(text)
    assert redact_text(once) == (once, [])


def test_redact_whole_jwt():
    jwt = (
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0."
        "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
    )
    out, reps = redact_text(f"token {jwt}")
    assert out == "token <JWT>" and [r.kind for r in reps] == ["jwt"]


# ---- adversarial round 2 (m1d-r2) ----


@pytest.mark.parametrize(
    "text",
    [
        "token: gpt4o-mini2024",
        "api_key: v2beta1release",
        "token = tokens[0]",
        "secret = settings.secret2fa",
        "pwd: /Users/me/project1",
        "max_tokens: 4096",
        "Token: 4k-context",
        "access_key = AWS_KEY_ID_2",
        "token: YOUR_TOKEN_123",
        "secret = /etc/app/secret-file-2024.pem",
        "The secret=sauce2024 is patience",
        "the bearer instrument2024",
        "http://localhost:8080@x",
        "Basic configuration is enough",
    ],
    ids=[
        "model",
        "api-version",
        "index",
        "attr",
        "pwd-path",
        "count",
        "context",
        "caps-var",
        "caps-placeholder",
        "path",
        "prose",
        "bearer-prose",
        "port",
        "basic-prose",
    ],
)
def test_redact_r2_leaves_code_and_prose_alone(text):
    assert redact_text(text) == (text, [])


@pytest.mark.parametrize(
    ("text", "secret"),
    [
        ("PASSWORD=CorrectHorseBatteryStaple", "CorrectHorseBatteryStaple"),
        ('client_secret = "GOCSPX-AbCdEfGhIjKlMnOpQrStUvWx"', "GOCSPX-AbCdEfGhIjKlMnOpQrStUvWx"),
        ("Authorization: Basic dXNlcjpwYXNzd29yZDEyMw==", "dXNlcjpwYXNzd29yZDEyMw=="),
        ("mytool --api-key a1b2c3d4e5f6Q", "a1b2c3d4e5f6Q"),
        ("gh auth login --token Zx9Lq2Wv8RtA", "Zx9Lq2Wv8RtA"),
        ("app --password=Zx9Lq2Wv8RtA", "Zx9Lq2Wv8RtA"),
        ("app --secret Zx9Lq2Wv8RtA", "Zx9Lq2Wv8RtA"),
        ("mysql -u root -pS3cretPass9", "S3cretPass9"),
        ("password: hunter22x", "hunter22x"),
        ("export STRIPE_SECRET=whsec_AbCdEf123456", "whsec_AbCdEf123456"),
    ],
    ids=[
        "all-letters",
        "gocspx",
        "basic",
        "flag-api-key",
        "flag-token",
        "flag-password-eq",
        "flag-secret",
        "mysql-p",
        "password-name",
        "whsec",
    ],
)
def test_redact_r2_catches(text, secret):
    out, reps = redact_text(text)
    assert secret not in out and reps


def test_redact_r2_token_index_syntax_intact():
    assert redact_text("token = tokens[0]")[0] == "token = tokens[0]"


@pytest.mark.parametrize("char", ["­", "⁠", "᠎"], ids=["shy", "wj", "mvs"])
def test_redact_r2_invisible_split_chars(char):
    key = "sk-proj-Ab3dEf6hIj" + char + "9kLm2nOp5qRs8tUv1wXy4z"
    assert redact_text(f"use {key} now")[0] == "use <OPENAI_API_KEY> now"


@pytest.mark.parametrize(
    "text", ["KEY-" + KEY, "MY_" + KEY], ids=["after-caps-hyphen", "after-caps-underscore"]
)
def test_redact_r2_key_glued_to_caps_name(text):
    out, _ = redact_text(text)
    assert KEY not in out


def test_redact_r2_line_join_never_swallows_next_line():
    text = "Run the command sk-learn\ninstall-package-12345"
    assert redact_text(text) == (text, [])


def test_redact_r2_key_split_over_three_lines_is_flagged_not_partial():
    text = "use sk-proj-Ab3dEf\n6hIj9kLm2nOp\n5qRs8tUv1wXy4z"
    out, reps = redact_text(text)
    assert out == text
    assert [(r.kind, r.placeholder) for r in reps] == [("split_key", "(not replaced)")]


# ---- round 3 (m1d-r3) ----


def test_redact_fullwidth_hyphen_key_is_replaced_in_full():
    key = "sk－proj－Ab3dEf6hIj9kLm2nOp5qRs8tUv1wXy4z"
    out, reps = redact_text(f"use {key} now")
    assert out == "use <OPENAI_API_KEY> now" and [r.kind for r in reps] == ["openai"]


def test_redact_fullwidth_letters_and_zero_width_together():
    key = "ｓｋ-proj-Ab3dEf​6hIj9kLm2nOp5qRs8tUv1wXy4z"
    out, _ = redact_text(f"[{key}]")
    assert out == "[<OPENAI_API_KEY>]"


def test_redact_nfkc_never_changes_other_text():
    text = "café ＡＢＣ ﬁle ① and sk-learn"
    assert redact_text(text) == (text, [])


# ---- --work --in --out: stage 6 staging without a shell redirect (skill audit 5 fix 5) ----


def _redact_file(*args: str):
    return CliRunner().invoke(app, ["redact", *args])


@pytest.fixture(params=["work", "packs"])
def run_folder(request, sw_home) -> Path:
    path = sw_home / request.param / "demo-20261012-120000"
    WorkDir(path).ensure()
    (path / "draft" / "references").mkdir(parents=True)
    (path / "draft" / "references" / "setup.md").write_text(f"key {KEY}\n", encoding="utf-8")
    return path


def test_redact_in_out_writes_the_redacted_file_and_its_folders(run_folder):
    src = run_folder / "draft" / "references" / "setup.md"
    out = run_folder / "staging" / "demo" / "references" / "setup.md"
    r = _redact_file("--work", str(run_folder), "--in", str(src), "--out", str(out))
    assert r.exit_code == 0, r.output
    assert r.stdout == ""
    text = out.read_text(encoding="utf-8")
    assert "<OPENAI_API_KEY>" in text and KEY not in text and text.endswith("\n")


def test_redact_in_out_respects_home(tmp_path, sw_home):
    home = tmp_path / "other" / ".skipwatch"
    work = home / "work" / "demo-20261012-120000"
    WorkDir(work).ensure()
    (work / "draft").mkdir()
    (work / "draft" / "SKILL.md").write_text("hi\n", encoding="utf-8")
    out = work / "staging" / "demo" / "SKILL.md"
    args = ["--work", str(work), "--in", str(work / "draft" / "SKILL.md"), "--out", str(out)]
    r = CliRunner().invoke(app, ["--home", str(home), "redact", *args])
    assert r.exit_code == 0, r.output
    assert out.read_text(encoding="utf-8") == "hi\n"


def _refusals(tmp_path: Path, work: Path) -> list[tuple[Path, Path, Path]]:
    src = work / "draft" / "references" / "setup.md"
    out = work / "staging" / "demo" / "setup.md"
    outside = tmp_path / "outside.md"
    outside.write_text("keep\n", encoding="utf-8")
    elsewhere = tmp_path / "elsewhere" / "demo-20261012-120000"
    WorkDir(elsewhere).ensure()
    (elsewhere / "draft").mkdir()
    (elsewhere / "draft" / "a.md").write_text("x\n", encoding="utf-8")
    cases = [
        (elsewhere, elsewhere / "draft" / "a.md", elsewhere / "staging" / "a.md"),
        (work, src, outside),
        (work, src, work / "staging" / ".." / ".." / "escape.md"),
        (work, src, work / "draft" / "copy.md"),
        (work, src, work / "staging"),
        (work, src, work / "stages.json"),
        (work, outside, out),
        (work, work / "stages.json", out),
        (work, work / "draft" / ".." / "stages.json", out),
        (work, work / "draft" / "missing.md", out),
        (work, work / "draft", out),
    ]
    try:
        link_out = work / "staging" / "link.md"
        link_out.parent.mkdir(parents=True, exist_ok=True)
        link_out.symlink_to(outside)
        link_in = work / "draft" / "link.md"
        link_in.symlink_to(outside)
        staging_dir_link = work / "staging" / "dirlink"
        staging_dir_link.symlink_to(tmp_path, target_is_directory=True)
        cases += [
            (work, src, link_out),
            (work, link_in, out),
            (work, src, staging_dir_link / "evil.md"),
        ]
    except OSError:
        pass
    return cases


def test_redact_in_out_refuses_paths_outside_the_folder_and_writes_nothing(tmp_path, run_folder):
    for work, src, out in _refusals(tmp_path, run_folder):
        before = out.read_bytes() if out.is_file() else None
        r = _redact_file("--work", str(work), "--in", str(src), "--out", str(out))
        assert r.exit_code == 64, (src, out, r.output)
        assert (out.read_bytes() if out.is_file() else None) == before, out
    assert (tmp_path / "outside.md").read_text(encoding="utf-8") == "keep\n"
    assert not (tmp_path / "escape.md").exists() and not (tmp_path / "evil.md").exists()
    assert not (run_folder / "draft" / "copy.md").exists()


@pytest.mark.parametrize(
    "args",
    [
        ("--stdin", "--work", "W", "--in", "I", "--out", "O"),
        ("--work", "W", "--in", "I"),
        ("--work", "W", "--out", "O"),
        ("--in", "I", "--out", "O"),
        ("--stdin", "--out", "O"),
    ],
)
def test_redact_modes_do_not_mix(run_folder, args):
    real = {
        "W": str(run_folder),
        "I": str(run_folder / "draft" / "references" / "setup.md"),
        "O": str(run_folder / "staging" / "x.md"),
    }
    r = _redact_file(*[real.get(a, a) for a in args])
    assert r.exit_code == 64
    assert not (run_folder / "staging").exists()


def test_redact_message_hides_secret_env_values_of_any_shape():
    from skipwatch.redact import redact_message

    env = {"MEM0_API_KEY": "plainvalue-123", "TREG_TOKEN": "short", "HOME": "/Users/x"}
    out = redact_message("key plainvalue-123 home /Users/x tok short", env)
    assert "plainvalue-123" not in out and "<SECRET>" in out
    assert "/Users/x" in out  # not a secret name
    assert "short" in out  # under 8 characters: too short to replace safely
    key = "sk-proj-" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8S9t0"
    assert key not in redact_message(f"bad {key}", {})  # redact_text patterns still apply
