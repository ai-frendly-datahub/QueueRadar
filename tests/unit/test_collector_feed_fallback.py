from __future__ import annotations

from unittest.mock import Mock, patch

from queueradar.collector import _collect_single
from queueradar.models import Source


def test_collect_single_falls_back_to_title_and_entry_id_url() -> None:
    source = Source(name="Fallback Feed", type="rss", url="https://example.com/feed")
    mock_response = Mock()
    mock_response.content = b"""<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Fallback title</title>
      <guid>https://example.com/item-1</guid>
    </item>
  </channel>
</rss>"""
    mock_response.raise_for_status = Mock()

    with patch("queueradar.collector._fetch_url_with_retry", return_value=mock_response):
        articles = _collect_single(source, category="queue", limit=5, timeout=5)

    assert len(articles) == 1
    assert articles[0].title == "Fallback title"
    assert articles[0].summary == "Fallback title"
    assert articles[0].link == "https://example.com/item-1"


def test_collect_single_falls_back_to_source_url_for_invalid_entry_id() -> None:
    source = Source(name="Fallback Feed", type="rss", url="https://example.com/feed")
    mock_response = Mock()
    mock_response.content = b"""<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Fallback title</title>
      <guid>invalid-guid</guid>
    </item>
  </channel>
</rss>"""
    mock_response.raise_for_status = Mock()

    with patch("queueradar.collector._fetch_url_with_retry", return_value=mock_response):
        articles = _collect_single(source, category="queue", limit=5, timeout=5)

    assert len(articles) == 1
    assert articles[0].title == "Fallback title"
    assert articles[0].summary == "Fallback title"
    assert articles[0].link == "https://example.com/feed"
