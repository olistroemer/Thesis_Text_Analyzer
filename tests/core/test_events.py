"""EventBus tests (SDD Sec. 5.5, ADR-0013)."""

from tta.core import events


def test_typed_subscription():
    bus = events.EventBus()
    seen = []
    bus.subscribe(events.ThesisStarted, seen.append)
    bus.publish(events.ThesisStarted(thesis_id=1))
    bus.publish(events.ModuleStarted(thesis_id=1, module_name="mod_x"))  # not subscribed
    assert seen == [events.ThesisStarted(thesis_id=1)]


def test_catch_all_subscription():
    bus = events.EventBus()
    seen = []
    bus.subscribe_all(seen.append)
    bus.publish(events.ThesisStarted(thesis_id=1))
    bus.publish(events.RunCancelled(completed=2, skipped=3))
    assert len(seen) == 2


def test_failing_handler_does_not_break_the_run(caplog):
    bus = events.EventBus()
    seen = []

    def broken(event):
        raise RuntimeError("adapter bug")

    bus.subscribe(events.ThesisStarted, broken)
    bus.subscribe(events.ThesisStarted, seen.append)
    bus.publish(events.ThesisStarted(thesis_id=1))
    assert seen == [events.ThesisStarted(thesis_id=1)]  # later handlers still ran
    assert any("event handler" in r.message for r in caplog.records)
