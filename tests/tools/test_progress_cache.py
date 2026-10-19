from __future__ import annotations

from pathlib import Path

import pytest

from tools._socom.progress_cache import ensure_cache, query
from tools._socom.util import SocomError


def test_progress_cache_answers_queries_and_refuses_writes(root: Path) -> None:
    path = ensure_cache(root)
    assert path.is_file()
    result = query(root, "select count(*) from symbols")
    assert result["rows"] == [[21_894]]
    rows = query(root, "select name from symbols where value = 1572864 and type = 'FUNC'")["rows"]
    assert ["GetEventString__8CAiEventFQ28CAiEvent5EVENT"] in rows
    assert query(root, "select count(*) from work_items where kind = 'recon-plan-group'")["rows"] == [[329]]
    with pytest.raises(SocomError):
        query(root, "delete from symbols")
    with pytest.raises(SocomError):
        query(root, "select 1; select 2")
    # A second call reuses the fresh cache.
    assert ensure_cache(root) == path
