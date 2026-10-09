from skipwatch.checks import style
from skipwatch.models import Config, StyleConfig
from tests.unit.checks.conftest import EM_DASH, context_for, make_case

EN_DASH = "\u2013"


def _run(tmp_path, edit=None, forbid=None, after=None):
    staging, work = make_case(tmp_path, edit=edit)
    if after is not None:
        after(staging)
    ctx = context_for(staging, work)
    if forbid is not None:
        ctx.config = Config(style=StyleConfig(forbid=forbid))
    return style.run(ctx)


def _msgs(r):
    return [i.msg for i in r.items]


def test_style_fails_on_em_dash_in_prose(tmp_path):
    r = _run(tmp_path, lambda s: s.replace("Sets up a tiny", f"Sets up a {EM_DASH} tiny"))
    assert not r.ok and _msgs(r) == ["em-dash in prose of SKILL.md (1 time)"]


def test_style_fails_on_en_dash_when_forbidden(tmp_path):
    r = _run(
        tmp_path,
        lambda s: s.replace("Sets up a tiny", f"Sets up a {EN_DASH} tiny"),
        forbid=["em-dash", "en-dash"],
    )
    assert not r.ok and _msgs(r) == ["en-dash in prose of SKILL.md (1 time)"]


def test_style_fails_on_custom_literal(tmp_path):
    r = _run(
        tmp_path,
        lambda s: s.replace("Sets up a tiny", "Utilize a tiny utilize"),
        forbid=["utilize"],
    )
    assert not r.ok and _msgs(r) == ["'utilize' in prose of SKILL.md (1 time)"]


def test_style_fails_on_em_dash_in_reference_prose(tmp_path):
    def dirty(staging):
        source = staging / "references" / "source.md"
        source.write_text(f"# Evidence {EM_DASH} notes\n", encoding="utf-8")

    r = _run(tmp_path, after=dirty)
    assert not r.ok and _msgs(r) == ["em-dash in prose of references/source.md (1 time)"]


def test_style_passes(tmp_path):
    r = _run(tmp_path)
    assert r.ok and r.items == [] and r.check == "style"


def test_style_exempts_quote_blocks_in_procedure(tmp_path):
    r = _run(
        tmp_path,
        lambda s: (
            s.replace("skipdemo init --name hello", f"skipdemo init {EM_DASH} hello")
            .replace("> Finally, click run", f"> Finally {EM_DASH} click run")
            .replace("Initialise the project.", f"Initialise the `{EM_DASH}` project.")
        ),
    )
    assert r.ok, _msgs(r)


def test_style_exempts_transcript(tmp_path):
    def spoken(staging):
        (staging / "references" / "transcript.md").write_text(
            f"[00:01] well {EM_DASH} as I said\n", encoding="utf-8"
        )

    assert _run(tmp_path, after=spoken).ok


def test_style_off_when_forbid_empty(tmp_path):
    r = _run(
        tmp_path, lambda s: s.replace("Sets up a tiny", f"Sets up a {EM_DASH} tiny"), forbid=[]
    )
    assert r.ok


# ---- adversarial review (m1d-review) ----

ATTR = "## Attribution"


def _before_attribution(text):
    return lambda s: s.replace(ATTR, text + "\n\n" + ATTR, 1)


def test_style_fails_on_blockquote_outside_procedure(tmp_path):
    r = _run(tmp_path, _before_attribution(f"> Generated prose {EM_DASH} hidden in a quote."))
    assert not r.ok and _msgs(r) == ["em-dash in prose of SKILL.md (1 time)"]


def test_style_fails_on_fence_outside_procedure(tmp_path):
    r = _run(tmp_path, _before_attribution(f"```\nGenerated {EM_DASH} prose\n```"))
    assert not r.ok


def test_style_fails_on_inline_code_outside_procedure(tmp_path):
    r = _run(tmp_path, _before_attribution(f"Generated prose `{EM_DASH}` here."))
    assert not r.ok


def test_style_fails_on_unclosed_fence(tmp_path):
    r = _run(
        tmp_path,
        lambda s: s.replace("## Worked example", f"```\n\nRest {EM_DASH} x\n\n## Worked example"),
    )
    assert not r.ok


def test_style_fails_on_description(tmp_path):
    r = _run(tmp_path, lambda s: s.replace("description: Use", f"description: Use {EM_DASH}", 1))
    assert not r.ok and _msgs(r) == ["em-dash in the description (1 time)"]


def test_style_fails_on_nested_reference_and_asset_markdown(tmp_path):
    def extra(staging):
        (staging / "references" / "sub").mkdir()
        (staging / "references" / "sub" / "a.md").write_text(f"x {EM_DASH} y\n", encoding="utf-8")
        (staging / "assets" / "prompt.md").write_text(f"x {EM_DASH} y\n", encoding="utf-8")

    r = _run(tmp_path, after=extra)
    assert not r.ok and _msgs(r) == [
        "em-dash in prose of assets/prompt.md (1 time)",
        "em-dash in prose of references/sub/a.md (1 time)",
    ]


def test_style_fails_on_quote_before_step_one(tmp_path):
    r = _run(
        tmp_path,
        lambda s: s.replace("## Procedure\n\n", f"## Procedure\n\n> Intro {EM_DASH} prose.\n\n", 1),
    )
    assert not r.ok


def test_style_fails_on_quote_in_inferred_step(tmp_path):
    r = _run(
        tmp_path,
        lambda s: s.replace("[spoken 00:49]", "[inferred]").replace(
            "> Finally, click run", f"> Finally {EM_DASH} click run"
        ),
    )
    assert not r.ok
