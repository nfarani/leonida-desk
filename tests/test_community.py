"""Community post classification: only an observable find may become COMMUNITY_DISCOVERY."""
import pytest

from research import llm
from research.community import classify_post
from research.models import Story
from research.normalise import normalise
from research.pipeline import run
from research.verify import clip, evidence, heuristic_label


def reddit(make, title, snippet="", **kw):
    """A community post from an always-relevant feed (like r/GTA6): skips the keyword relevance filter."""
    it = make(title, "forum.test", "community", snippet=snippet, **kw)
    it.always_relevant = True
    return it


def post(make, cfg, title, snippet="", **kw):
    new, _, _ = normalise([reddit(make, title, snippet, **kw)], cfg, set())
    return new[0]


@pytest.mark.parametrize("title,snippet,ctype,label", [
    ("What will Leonida's state capital be?", "Curious what everyone thinks.", "QUESTION", "SPECULATION"),
    ("Me when GTA 6 finally drops 😂", "", "MEME", "SPECULATION"),
    ("Theory: the recurring Zynthcorp brand points to a hidden storyline",
     "Anyone else think this is intentional?", "THEORY", "THEORY"),
    ("I hope GTA 6 has split screen co-op", "It would be so cool.", "WISHLIST", "SPECULATION"),
    ("Thoughts on the fatigue mechanic", "I feel like it could get annoying.", "DISCUSSION", "SPECULATION"),
    ("Just noticed a flamingo statue in the background of the Trailer 2 beach frame",
     "Pause at the synthetic timestamp and it is clearly there.", "OBSERVABLE_DISCOVERY", "COMMUNITY_DISCOVERY"),
])
def test_content_type_and_label(cfg, make, title, snippet, ctype, label):
    it = post(make, cfg, title, snippet)
    assert classify_post(it, cfg) == ctype
    assert heuristic_label(Story(items=[it]), cfg) == label


def test_ordinary_discussion_can_never_be_community_discovery(cfg, make):
    for title in ("How will you play Jason and Lucia?", "Really excited to play GTA 6 on launch week",
                  "My girl the moment GTA 6 drops", "I made a concept map for a fan DLC"):
        s = Story(items=[post(make, cfg, title)])
        assert heuristic_label(s, cfg) != "COMMUNITY_DISCOVERY"
        # Even if Claude asks for it, the evidence ceiling refuses
        assert clip("COMMUNITY_DISCOVERY", evidence(s, cfg), "SPECULATION") == "THEORY"


def test_observable_discovery_can_be_community_discovery(cfg, make):
    s = Story(items=[post(make, cfg, "Spotted: the release date was corrected on the official trailer thumbnail")])
    assert heuristic_label(s, cfg) == "COMMUNITY_DISCOVERY"
    assert clip("CONFIRMED", evidence(s, cfg), "SPECULATION") == "COMMUNITY_DISCOVERY"


def test_claude_cannot_promote_a_question_to_discovery(cfg, make, monkeypatch):
    s = Story(items=[post(make, cfg, "Which location do you think you'll enjoy the most?")],
              verification_status="SPECULATION")
    fake = '[{"id": "%d", "label": "COMMUNITY_DISCOVERY", "hook": "Fans have spotted something"}]' % id(s)
    monkeypatch.setattr(llm, "_call", lambda *a, **k: fake)
    llm.editorial(cfg, [s])
    assert s.verification_status == "THEORY"


def test_reddit_post_linking_credible_news(cfg, make):
    article = make("Synthetic Studio delays GTA 6 to Zeptember 2031", "tierone-a.test", hours_ago=3, path="delay")
    link = post(make, cfg, "Well, this is not great", "[links to https://tierone-a.test/delay]")
    assert classify_post(link, cfg) == "NEWS_LINK"
    # On its own the post is only a lead: the article is not attached, so no credit for it yet
    assert heuristic_label(Story(items=[link]), cfg) == "SPECULATION"
    # Run together, the post attaches to the article's story and the label comes from the journalism
    _, recs = run(cfg, use_llm=False, items_override=[article, reddit(
        make, "Well, this is not great", "[links to https://tierone-a.test/delay]")])
    assert len(recs) == 1
    story = recs[0][0]
    assert len(story.items) == 2
    assert story.verification_status in ("HIGH_CONFIDENCE_REPORT", "CREDIBLE_RUMOUR")


def test_chatter_feeds_demand_but_is_not_recommended(cfg, make):
    items = [
        make("Synthetic Studio delays GTA 6 to Zeptember 2031", "tierone-a.test", hours_ago=2, path="d1"),
        # A meme about that story: attaches to it and lifts its demand
        reddit(make, "Me when Synthetic Studio delays GTA 6 to Zeptember 2031 😂", path="m1",
               engagement={"score": 4000, "comments": 600}),
        # Standalone chatter with huge engagement: still not a story
        reddit(make, "Me when my boss asks why I booked launch week off 😂", path="m2",
               engagement={"score": 9000, "comments": 2000}),
        reddit(make, "What car will you steal first?", path="q1", engagement={"score": 7000, "comments": 3000}),
    ]
    path, recs = run(cfg, use_llm=False, items_override=items)
    assert len(recs) == 1
    story = recs[0][0]
    assert {i.url.rsplit("/", 1)[-1] for i in story.items} == {"d1", "m1"}
    assert story.dims["existing_demand"] > 0.9
    text = path.read_text()
    assert "Fans have spotted something" not in text
    assert "Held as community chatter (demand signal only, not recommended): 2" in text
    assert "MEME 2" in text and "QUESTION 1" in text
