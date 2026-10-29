# Daytrader fork

The `daytrader` branch is based on upstream Invisible Playwright **v0.43.0**. Upstream history and licenses are retained. This is a source fork, not a new PyPI release; package versions and the upstream core version requirement are unchanged.

## Focused fixes

- Publish a popup's opener reference under the opener's existing close lock, or omit a reference already announced closed. Release that lock before native event/RPC work.
- Reserve one worker for terminal `close` messages so four blocked ordinary workers cannot prevent the close that releases them. Keep the existing dispatch, reply, error and shutdown paths.
- Require a single match for selector-based ARIA snapshots. Whole-document snapshots and upstream atomic locator reads remain unchanged.

The paired [invisible_core fork](https://github.com/dkoukola/invisible_core/tree/daytrader), based on **v53.48.0**, contains the retained context ownership, page-detach and hidden-selector fixes. Installing this wrapper alone can resolve the unmodified upstream core from PyPI; install both fork revisions when reproducing the complete Daytrader dependency set. Pin commit IDs for reproducible installations.

## Focused verification

With both source forks installed into the same Python environment and `pytest` available, run from this repository:

```console
python -m pytest -q tests/test_juggler_popup_opener_race.py tests/test_juggler_close_admission.py tests/test_juggler_aria_strictness.py tests/test_juggler_transport.py
```

The new regressions need no browser, network service or private profile. They cover popup publication ordering and failure cleanup; mixed channel/fused worker saturation, close errors, cancelled futures and shutdown; ARIA strictness and the unchanged whole-document path. The existing transport suite uses its default non-e2e selection. This is focused verification, not a claim that the entire upstream suite is green.

Daytrader's separate native qualification exercised the matching Firefox-53 engine with isolated profiles: navigation, retained element handles, close admission, downloads, locator reads, humanized input, guarded evaluation and page CSP. Its application-specific bridge and deployment files are intentionally not part of this fork.
