"""Doctor names the plugin and engine versions and warns when they differ (M6 upgrades)."""

import json
from datetime import date

from skipwatch import doctor
from tests.unit.test_doctor import P

TODAY = date(2026, 10, 9)


def plugin_root(tmp_path, version: str):
    root = tmp_path / "plugin root"
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin/plugin.json").write_text(
        json.dumps({"name": "skipwatch", "version": version})
    )
    return str(root)


def component(report, name):
    [found] = [c for c in report.components if c.name == name]
    return found


def test_reports_plugin_and_engine_versions(tmp_path):
    r = doctor.build_report(P(engine="0.2.0"), TODAY, plugin_root(tmp_path, "0.2.0"))
    assert component(r, "skipwatch").version == "0.2.0"
    assert component(r, "plugin").version == "0.2.0" and component(r, "plugin").found
    assert not any("plugin" in w for w in r.warnings)
    lines = doctor.render_table(r)
    assert "  skipwatch: 0.2.0" in lines and "  plugin: 0.2.0" in lines


def test_engine_defaults_to_the_running_package():
    assert P().engine == doctor.skipwatch.__version__


def test_version_mismatch_warns_with_the_reinstall_fix(tmp_path):
    root = plugin_root(tmp_path, "0.2.0")
    r = doctor.build_report(P(engine="0.1.0"), TODAY, root)
    [warning] = [w for w in r.warnings if "plugin" in w]
    assert "plugin 0.2.0" in warning and "engine 0.1.0" in warning
    assert f'uv sync --inexact --project "{root}" --reinstall-package skipwatch' in warning


def test_no_plugin_root_reports_no_plugin_and_no_warning():
    r = doctor.build_report(P(engine="0.1.0"), TODAY, None)
    plugin = component(r, "plugin")
    assert not plugin.found and plugin.version is None
    assert plugin.detail == "not running from a plugin"
    assert not any("plugin" in w for w in r.warnings)


def test_unreadable_plugin_json_never_stops_doctor(tmp_path):
    root = tmp_path / "broken"
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin/plugin.json").write_text("{not json")
    r = doctor.build_report(P(engine="0.1.0"), TODAY, str(root))
    assert component(r, "plugin").version is None
    assert not any("plugin" in w for w in r.warnings)
    missing = doctor.build_report(P(engine="0.1.0"), TODAY, str(tmp_path / "absent"))
    assert component(missing, "plugin").version is None
