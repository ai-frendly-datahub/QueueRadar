from __future__ import annotations

from pathlib import Path

import pytest

from queueradar.models import Article
from queueradar.search_index import SearchIndex


@pytest.mark.integration
def test_search_index_integration(
    tmp_path: Path,
    sample_articles: list[Article],
) -> None:
    """Test search index integration: index articles → query → verify results."""
    search_db = tmp_path / "search.db"
    index = SearchIndex(search_db)

    for article in sample_articles:
        index.upsert(
            link=article.link,
            title=article.title,
            body=article.summary,
        )

    results = index.search("대기시간", limit=10)
    assert len(results) > 0

    results_hospital = index.search("병원", limit=10)
    assert len(results_hospital) > 0

    results_empty = index.search("nonexistent_keyword_xyz", limit=10)
    assert len(results_empty) == 0

    index.close()
