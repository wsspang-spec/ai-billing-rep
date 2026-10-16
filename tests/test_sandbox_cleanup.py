"""Daytona sandboxes must not leak: one shared checks sandbox, and a redeploy replaces the portal. Offline: a fake client."""

import json

import pytest
from daytona import DaytonaNotFoundError, SandboxState

from billingrep import checks, portal_deploy


class FakeSandbox:
    def __init__(self, id, state=SandboxState.STARTED, created_at="2026-10-16T19:00:00Z", role="checks", auto_stop=15):
        self.id, self.state, self.created_at, self.auto_stop_interval = id, state, created_at, auto_stop
        self.labels = {"app": "ai-billing-rep", "role": role}

    def wait_for_sandbox_start(self, timeout=60):
        pass

    def set_autostop_interval(self, minutes):
        self.auto_stop_interval = minutes


class FakeDaytona:
    def __init__(self, sandboxes=(), start_fails=False):
        self.sandboxes = list(sandboxes)
        self.start_fails = start_fails
        self.queries, self.started, self.deleted, self.created = [], [], [], []

    def list(self, query):
        self.queries.append(query)
        return iter(self.sandboxes)

    def get(self, id):
        for sb in self.sandboxes:
            if sb.id == id:
                return sb
        raise DaytonaNotFoundError(f"Sandbox with ID or name {id} not found")

    def start(self, sb, timeout=60):
        if self.start_fails:
            raise RuntimeError("would not start")
        self.started.append(sb.id)

    def delete(self, sb, timeout=60, wait=False):
        self.deleted.append(sb.id)

    def create(self, params, timeout=60):
        self.created.append(params)
        return FakeSandbox(f"new-{len(self.created)}")


@pytest.fixture
def fake(monkeypatch):
    """Point checks._get_sandbox at a FakeDaytona; set .sandboxes on it before calling."""
    d = FakeDaytona()
    monkeypatch.setenv("DAYTONA_API_KEY", "test")
    monkeypatch.setattr("daytona.Daytona", lambda config: d)
    monkeypatch.setattr(checks, "_sandbox", None)
    return d


def test_find_reuses_the_newest_running_sandbox():
    d = FakeDaytona([FakeSandbox("old", created_at="2026-10-16T18:00:00Z"),
                     FakeSandbox("broken", SandboxState.ERROR, created_at="2026-10-16T20:00:00Z"),
                     FakeSandbox("new", created_at="2026-10-16T19:00:00Z")])
    assert checks._find(d).id == "new"
    assert d.queries[0].labels == checks.LABELS


def test_find_skips_the_sandbox_that_just_failed():
    d = FakeDaytona([FakeSandbox("old", created_at="2026-10-16T18:00:00Z"), FakeSandbox("new")])
    assert checks._find(d, skip="new").id == "old"


def test_find_starts_a_stopped_sandbox():
    d = FakeDaytona([FakeSandbox("s", SandboxState.STOPPED)])
    assert checks._find(d).id == "s" and d.started == ["s"]


def test_find_deletes_a_stopped_sandbox_that_will_not_start():
    d = FakeDaytona([FakeSandbox("s", SandboxState.STOPPED)], start_fails=True)
    assert checks._find(d) is None and d.deleted == ["s"]


def test_restarts_create_one_sandbox_then_reuse_it(fake):
    first = checks._get_sandbox()
    assert len(fake.created) == 1 and fake.created[0].auto_stop_interval == checks.AUTO_STOP
    assert fake.created[0].labels == checks.LABELS and fake.created[0].ephemeral

    fake.sandboxes = [first]
    checks._sandbox = None  # a restarted server process
    assert checks._get_sandbox() is first and len(fake.created) == 1


def test_reused_sandbox_from_older_code_gets_the_short_auto_stop(fake):
    fake.sandboxes = [FakeSandbox("legacy", auto_stop=120)]
    assert checks._get_sandbox().auto_stop_interval == checks.AUTO_STOP and not fake.created


@pytest.fixture
def cache(tmp_path, monkeypatch):
    path = tmp_path / "portal.json"
    monkeypatch.setattr(portal_deploy, "CACHE", path)
    return path


def test_delete_cached_deletes_the_old_portal(cache):
    cache.write_text(json.dumps({"sandbox_id": "p1"}))
    d = FakeDaytona([FakeSandbox("p1", role="synthetic-portal")])
    portal_deploy._delete_cached(d)
    assert d.deleted == ["p1"]


def test_delete_cached_never_deletes_another_role(cache):
    cache.write_text(json.dumps({"sandbox_id": "c1"}))
    d = FakeDaytona([FakeSandbox("c1", role="checks")])
    portal_deploy._delete_cached(d)
    assert d.deleted == []


def test_delete_cached_ignores_a_portal_that_is_already_gone(cache):
    cache.write_text(json.dumps({"sandbox_id": "gone"}))
    portal_deploy._delete_cached(FakeDaytona())


def test_delete_cached_stops_the_deploy_on_other_errors(cache):
    class RateLimited(FakeDaytona):
        def delete(self, sb, timeout=60, wait=False):
            raise RuntimeError("rate limited")

    cache.write_text(json.dumps({"sandbox_id": "p1"}))
    with pytest.raises(RuntimeError):
        portal_deploy._delete_cached(RateLimited([FakeSandbox("p1", role="synthetic-portal")]))


def test_deploy_replaces_the_cached_portal_and_cleans_up_a_failed_one(cache, monkeypatch):
    cache.write_text(json.dumps({"sandbox_id": "p1"}))
    d = FakeDaytona([FakeSandbox("p1", role="synthetic-portal")])
    monkeypatch.setattr(portal_deploy, "_client", lambda: d)

    monkeypatch.setattr(portal_deploy, "_serve", lambda sb: "https://portal")
    assert portal_deploy.deploy() == "https://portal"
    assert d.deleted == ["p1"] and json.loads(cache.read_text())["sandbox_id"] == "new-1"

    def fail(sb):
        raise RuntimeError("portal did not answer")
    monkeypatch.setattr(portal_deploy, "_serve", fail)
    with pytest.raises(RuntimeError):
        portal_deploy.deploy()
    assert d.deleted[-1] == "new-2"  # the failed portal is not left running
