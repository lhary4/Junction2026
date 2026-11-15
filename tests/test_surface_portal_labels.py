"""What is synthetic says so on the kitchen order page: the mock-up notice is always on screen, and the sample food
trends of the Spotlight card name no news service."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SURFACE = ROOT / "surface"
STATIC = SURFACE / "static"


def test_the_mock_up_notice_is_in_the_header_not_only_in_the_teams_strip():
    html = (STATIC / "portal.html").read_text(encoding="utf-8")
    header = html[html.index('<header class="site">') : html.index("</header>")]
    notice = re.search(r'<p class="site__notice">([^<]+)</p>', header)

    assert notice, "the header must carry the notice: the strip at the bottom is below the fold at 1080p"
    for words in ("Concept mock-up", "Junction 2026", "synthetic data", "not a Valio Aimo service"):
        assert words in notice.group(1)


def test_the_sample_trends_say_they_are_synthetic_and_name_no_news_service():
    trends = json.loads((STATIC / "kitchen" / "trends.json").read_text(encoding="utf-8"))

    assert trends["trends"], "the Spotlight card needs at least one sample trend"
    for trend in trends["trends"]:
        assert "synthetic" in trend["source"].lower(), f"{trend['id']} must say it is a synthetic sample"
        assert "published_at" not in trend, "a sample trend was never published: no publication date"


def test_nothing_on_the_page_presents_a_sample_trend_as_a_news_headline():
    for path in (
        STATIC / "portal.js",
        STATIC / "portal.html",
        STATIC / "kitchen" / "trends.json",
        SURFACE / "assistant.py",
    ):
        assert "Google News" not in path.read_text(encoding="utf-8"), f"{path.name} names a news service"
