"""Fixtures scoped to the analysis-module tests.

Kept out of the shared `tests/conftest.py` on purpose: the memo below is a
concern of one module package, not of the whole suite.
"""

import pytest


@pytest.fixture(autouse=True)
def _clear_tokens_memo():
    """`_tokens` memoises the parsed tokens artefact per process (#69).

    Each test gets its own `tmp_path`, so the memo key - (path, st_mtime_ns,
    st_size) - already differs between tests on the CI filesystem and the
    suite passes without this. It is defensive: a filesystem with coarse
    mtime granularity (FAT, some network mounts) could let a rewritten
    `tokens.json` of identical size keep the previous key, which would show
    up as a baffling cross-test failure rather than as a cache bug.
    """
    from tta.core.modules import _tokens

    _tokens.clear_memo()
    yield
    _tokens.clear_memo()
