"""Stateful alert simulation with a read-only digest.

The module intentionally has no network, clock, or provider dependency. Event
sequence numbers and timestamps come from the fixture so the result is
reproducible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


@dataclass
class SubjectState:
    state: str = "unknown"
    fingerprint: str = ""
    acknowledged: bool = False
    notifications: int = 0
    transitions: list[dict[str, Any]] = field(default_factory=list)


def read_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            if not isinstance(item, dict) or not {"subject", "kind", "fingerprint"} <= item.keys():
                raise ValueError("event requires subject, kind, and fingerprint")
            events.append(item)
    return events


def _transition(subject: str, state: SubjectState, event: dict[str, Any], decision: str, reason: str) -> None:
    state.transitions.append({
        "subject": subject,
        "at": event.get("at", "fixture-time"),
        "kind": event["kind"],
        "decision": decision,
        "reason": reason,
    })


def simulate(events: Iterable[dict[str, Any]], acknowledgements: set[str] | None = None,
             resets: set[str] | None = None) -> dict[str, Any]:
    states: dict[str, SubjectState] = {}
    acknowledgements = acknowledgements or set()
    resets = resets or set()
    seen_events: set[str] = set()
    for subject in acknowledgements:
        states.setdefault(subject, SubjectState()).acknowledged = True
    for subject in resets:
        states.setdefault(subject, SubjectState()).acknowledged = False

    for event in events:
        subject = str(event["subject"])
        kind = str(event["kind"])
        fingerprint = str(event["fingerprint"])
        # A fixture timestamp is the delivery identity. Without it, retain
        # each event because two transitions can legitimately share a shape.
        if "at" in event:
            event_key = json.dumps(
                {"subject": subject, "kind": kind, "fingerprint": fingerprint, "at": event["at"]},
                sort_keys=True,
            )
            if event_key in seen_events:
                continue
            seen_events.add(event_key)
        state = states.setdefault(subject, SubjectState())
        if subject in acknowledgements:
            state.acknowledged = True
        if subject in resets:
            state.acknowledged = False

        if kind == "healthy":
            if state.state == "degraded":
                _transition(subject, state, event, "recover", "health returned")
            else:
                _transition(subject, state, event, "observe", "healthy state")
            state.state = "healthy"
            state.fingerprint = fingerprint
            state.acknowledged = False
            continue
        if kind != "degraded":
            raise ValueError(f"unsupported event kind: {kind}")

        changed = state.state != "degraded" or state.fingerprint != fingerprint
        if changed:
            decision, reason = "page", "new failure state"
            state.notifications += 1
            state.acknowledged = False
        elif state.acknowledged:
            decision, reason = "suppress", "acknowledged condition continues"
        else:
            decision, reason = "suppress", "unchanged failure state"
        _transition(subject, state, event, decision, reason)
        state.state = "degraded"
        state.fingerprint = fingerprint

    worklist = []
    for subject in sorted(states):
        state = states[subject]
        if state.state == "degraded":
            worklist.append({
                "subject": subject,
                "state": state.state,
                "acknowledged": state.acknowledged,
                "notifications": state.notifications,
                "latest_reason": state.transitions[-1]["reason"] if state.transitions else "none",
            })
    digest = {
        "subjects": len(states),
        "degraded": len(worklist),
        "notifications": sum(s.notifications for s in states.values()),
        "worklist": worklist,
        "transitions": sum(len(s.transitions) for s in states.values()),
    }
    return {"states": states, "digest": digest}


def serializable(result: dict[str, Any]) -> dict[str, Any]:
    return {"digest": result["digest"], "transitions": [
        transition
        for subject in sorted(result["states"])
        for transition in result["states"][subject].transitions
    ]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="simulate stateful alert lifecycles")
    parser.add_argument("events", nargs="?", default=str(Path(__file__).parents[1] / "fixtures" / "events.jsonl"))
    parser.add_argument("--json", action="store_true", help="emit a safe machine-readable digest")
    parser.add_argument("--ack", action="append", default=[])
    parser.add_argument("--reset", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        result = serializable(simulate(read_events(Path(args.events)), set(args.ack), set(args.reset)))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        digest = result["digest"]
        print(f"subjects={digest['subjects']} degraded={digest['degraded']} notifications={digest['notifications']}")
        for item in digest["worklist"]:
            marker = "acknowledged" if item["acknowledged"] else "needs-attention"
            print(f"{item['subject']}: {marker}; {item['latest_reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
