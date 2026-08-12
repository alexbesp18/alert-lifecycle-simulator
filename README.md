# Alert lifecycle simulator

This offline, stdlib-only demo models a small stateful alert policy. Repeated
copies of the same failure are suppressed, recovery closes the lifecycle, and
a changed failure fingerprint reopens it. A safe digest view exposes only the
synthetic subject, state, acknowledgement, reason, and notification count.

It demonstrates an operational pattern, not a production pager. All fixtures
are synthetic and authored for this repository. No network, credentials,
provider integration, or external service is used.

Run it from this directory:

```sh
PYTHONPATH=src python3 -m alert_lifecycle
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

`--json` emits the read-only digest and transition report. The digest is not
an uptime or service-health claim; its thresholds and event vocabulary are
illustrative only.
