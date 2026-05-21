from io import StringIO

from ntask._cache.diff import MissItem, MissReport
from ntask._render.log import LogRenderer


def test_log_renderer_summary_lists_failed_tasks():
    buf = StringIO()
    r = LogRenderer(stream=buf, use_color=False)
    r.summary(
        ran=2, cached=1, failed=2, skipped=0,
        failed_fqns=("scenario_a", "scenario_b"),
    )
    out = buf.getvalue()
    assert "failed=2" in out
    assert "failed tasks: scenario_a, scenario_b" in out


def test_log_renderer_summary_omits_failed_line_when_none_failed():
    buf = StringIO()
    r = LogRenderer(stream=buf, use_color=False)
    r.summary(ran=2, cached=1, failed=0, skipped=0)
    assert "failed tasks:" not in buf.getvalue()


def test_log_renderer_reports_running_and_ok():
    buf = StringIO()
    r = LogRenderer(stream=buf, use_color=False)
    r.on_running("build", cmd=None)
    r.on_ok("build", duration=0.42)
    out = buf.getvalue()
    assert "build" in out
    assert "running" in out.lower() or "+" in out


def test_log_renderer_reports_cache_hit():
    buf = StringIO()
    r = LogRenderer(stream=buf, use_color=False)
    r.on_cached("build", key="abc")
    assert "cached" in buf.getvalue().lower()


def test_log_renderer_reports_miss_report_inline():
    buf = StringIO()
    r = LogRenderer(stream=buf, use_color=False)
    report = MissReport(items=(
        MissItem(kind="input-modified", detail="src/a.py"),
        MissItem(kind="input-modified", detail="src/b.py"),
    ))
    r.on_miss_reason("build", report=report)
    out = buf.getvalue()
    assert "cache miss" in out.lower()
    assert "src/a.py" in out
    assert "+1 more" in out


def test_log_renderer_reports_first_run():
    buf = StringIO()
    r = LogRenderer(stream=buf, use_color=False)
    report = MissReport(items=(MissItem(kind="first-run", detail=""),))
    r.on_miss_reason("build", report=report)
    out = buf.getvalue()
    assert "first-run" in out.lower() or "first run" in out.lower()


def test_log_renderer_reports_failure():
    buf = StringIO()
    r = LogRenderer(stream=buf, use_color=False)
    r.on_failed("build", error=RuntimeError("boom"), tail_lines=["oops"])
    assert "failed" in buf.getvalue().lower()
    assert "boom" in buf.getvalue()


def test_log_renderer_summary():
    buf = StringIO()
    r = LogRenderer(stream=buf, use_color=False)
    r.summary(ran=2, cached=1, failed=0, skipped=0)
    assert "ran=2" in buf.getvalue()


def test_log_renderer_marks_remote_hit():
    buf = StringIO()
    r = LogRenderer(stream=buf, use_color=False)
    r.on_cached("build", key="abc12345abc12345abc12345abc12345", source="remote")
    out = buf.getvalue()
    assert "cached" in out.lower()
    assert "[remote]" in out


def test_log_renderer_local_default_no_marker():
    buf = StringIO()
    r = LogRenderer(stream=buf, use_color=False)
    r.on_cached("build", key="abc12345abc12345abc12345abc12345")
    out = buf.getvalue()
    assert "cached" in out.lower()
    assert "[remote]" not in out
