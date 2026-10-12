from pathlib import Path

import pytest
from PIL import Image, ImageCms
from typer.testing import CliRunner

from skipwatch.cli import app
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import Frame, FramesFile, Sampling
from skipwatch.skillframes import MAX_SKILL_FRAMES, SKILL_FRAME_WIDTH, copy_frames
from skipwatch.workdir import write_model


def frame_id(n: int) -> str:
    return f"f{n:06d}"


def make_work(tmp_path: Path, sizes: list[tuple[int, int]], mode: str = "RGB") -> Path:
    """A work folder with frames/<id>.jpg (a gradient, so resampling matters) and frames.json."""
    work = tmp_path / "work"
    (work / "frames").mkdir(parents=True)
    frames = []
    for n, (w, h) in enumerate(sizes, start=1):
        fid = frame_id(n)
        img = Image.new(mode, (w, h))
        img.putdata(
            [((x * 7 + n) % 256, (y * 3) % 256, (x + y) % 256) for y in range(h) for x in range(w)]
        )
        exif = Image.Exif()
        exif[0x010F] = "SomeCamera"  # Make
        icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        img.save(work / "frames" / f"{fid}.jpg", quality=95, exif=exif, icc_profile=icc)
        frames.append(
            Frame(id=fid, t=float(n), path=f"frames/{fid}.jpg", reason="scene", dhash="0" * 16)
        )
    write_model(
        work / "frames.json", FramesFile(sampling=Sampling(per_minute=3, max=60), frames=frames)
    )
    return work


def test_copy_frames_scales_to_960_and_is_idempotent(tmp_path):
    work = make_work(tmp_path, [(1280, 720), (1920, 1080)])
    with Image.open(work / "frames" / f"{frame_id(1)}.jpg") as src:
        assert "exif" in src.info and "icc_profile" in src.info  # so the checks below bite
    dest = tmp_path / "skill" / "frames"
    out = copy_frames(work, dest, [frame_id(1), frame_id(2)])
    assert out == [dest / f"{frame_id(1)}.jpg", dest / f"{frame_id(2)}.jpg"]
    for path in out:
        with Image.open(path) as img:
            assert img.size == (SKILL_FRAME_WIDTH, 540)
            assert img.mode == "RGB"
            assert "exif" not in img.info and "icc_profile" not in img.info
            assert len(img.getexif()) == 0
    first = [p.read_bytes() for p in out]
    again = copy_frames(work, dest, [frame_id(1), frame_id(2)])
    assert [p.read_bytes() for p in again] == first
    assert sorted(p.name for p in dest.iterdir()) == [f"{frame_id(1)}.jpg", f"{frame_id(2)}.jpg"]


def test_copy_frames_never_upscales(tmp_path):
    work = make_work(tmp_path, [(640, 360), (960, 600)])
    dest = tmp_path / "out"
    out = copy_frames(work, dest, [frame_id(1), frame_id(2)])
    sizes = []
    for path in out:
        with Image.open(path) as img:
            sizes.append(img.size)
            assert "exif" not in img.info and "icc_profile" not in img.info
    assert sizes == [(640, 360), (960, 600)]


def test_copy_frames_converts_to_rgb(tmp_path):
    work = make_work(tmp_path, [(1200, 400)])
    src = work / "frames" / f"{frame_id(1)}.jpg"
    Image.open(src).convert("CMYK").save(src)
    (out,) = copy_frames(work, tmp_path / "out", [frame_id(1)])
    with Image.open(out) as img:
        assert img.mode == "RGB" and img.size == (960, 320)


def test_copy_frames_caps_at_8(tmp_path):
    work = make_work(tmp_path, [(100, 50)] * 9)
    dest = tmp_path / "out"
    ids = [frame_id(n) for n in range(1, 10)]
    with pytest.raises(SkipwatchError) as exc:
        copy_frames(work, dest, ids)
    assert exc.value.code == ExitCode.USAGE
    assert not dest.exists()
    # the cap counts frames already in the folder; re-copying one of them is not a new frame
    copy_frames(work, dest, ids[:6])
    with pytest.raises(SkipwatchError):
        copy_frames(work, dest, ids[6:9])
    assert len(list(dest.glob("*.jpg"))) == 6
    copy_frames(work, dest, [ids[0], ids[6], ids[7]])
    assert len(list(dest.glob("*.jpg"))) == MAX_SKILL_FRAMES


def test_copy_frames_unknown_id_is_64(tmp_path):
    work = make_work(tmp_path, [(100, 50)])
    dest = tmp_path / "out"
    r = CliRunner().invoke(
        app,
        ["copy-frames", "--work", str(work), "--to", str(dest), frame_id(1), "f999999"],
    )
    assert r.exit_code == ExitCode.USAGE
    assert "f999999" in r.stderr
    assert not dest.exists()


def test_copy_frames_cli_copies(tmp_path):
    work = make_work(tmp_path, [(1280, 720)])
    dest = tmp_path / "out"
    r = CliRunner().invoke(
        app, ["copy-frames", "--work", str(work), "--to", str(dest), frame_id(1)]
    )
    assert r.exit_code == 0, r.stderr
    assert (dest / f"{frame_id(1)}.jpg").is_file()
    assert "Copied 1 frame" in r.stderr


def test_copy_frames_without_frames_json_is_7(tmp_path):
    with pytest.raises(SkipwatchError) as exc:
        copy_frames(tmp_path, tmp_path / "out", [frame_id(1)])
    assert exc.value.code == ExitCode.NO_CONTENT


@pytest.mark.parametrize("where", ["absolute", "parent"])
def test_copy_frames_refuses_paths_outside_the_frames_folder(tmp_path, where):
    work = make_work(tmp_path, [(100, 50), (100, 50)])
    outside = tmp_path / "secret.jpg"
    Image.new("RGB", (10, 10)).save(outside)
    frames = FramesFile.model_validate_json((work / "frames.json").read_text("utf-8"))
    frames.frames[1].path = str(outside) if where == "absolute" else "../secret.jpg"
    write_model(work / "frames.json", frames)
    dest = tmp_path / "out"
    with pytest.raises(SkipwatchError) as exc:
        copy_frames(work, dest, [frame_id(1), frame_id(2)])
    assert exc.value.code == ExitCode.USAGE
    assert frame_id(2) in exc.value.message
    assert not dest.exists()


def test_copy_frames_nul_in_a_frame_path_is_64_naming_the_frame(tmp_path):
    work = make_work(tmp_path, [(100, 50), (100, 50)])
    frames = FramesFile.model_validate_json((work / "frames.json").read_text("utf-8"))
    frames.frames[1].path = "frames/bad\x00.jpg"
    write_model(work / "frames.json", frames)
    dest = tmp_path / "out"
    r = CliRunner().invoke(
        app, ["copy-frames", "--work", str(work), "--to", str(dest), frame_id(1), frame_id(2)]
    )
    assert r.exit_code == ExitCode.USAGE, r.stderr
    assert frame_id(2) in r.stderr
    assert not dest.exists()
