#!/usr/bin/env python3
"""Rebuild the three sample articles from their evidence packets.

The samples were written on 05 Oct 2026 from sources that were opened and read that day. Every quote
below was checked word for word against the source page. This script exists so the samples can be
regenerated through the same checks as any other article; it is not part of the daily workflow.
The packets must exist first:
  article.py packet story:224 --also 205 232 143 148 --bucket BREAKING --angle-id love-interview
  article.py packet story:186 --bucket EXPLAINER --angle-id pegi-listing-explained
  article.py packet story:90 --also 224 205 232 143 148 --bucket EVERGREEN --angle-id evergreen:rockstar_history
"""
import _path  # noqa: F401
from research import articles as A
from research.config import load_config

cfg = load_config()
BYLINE = cfg["publishing"]["publication"]["byline"]


def src(packet, publisher, needle):
    """The stored source for a publisher whose URL contains `needle` (direct links, not aggregator ones)."""
    return next(s["id"] for s in packet["sources"] if s["publisher"] == publisher and needle in s["url"])


def opened(packet, sid, note=""):
    s = next(s for s in packet["sources"] if s["id"] == sid)
    s["opened"], s["opened_at"], s["note"] = True, A.iso(A.now_utc()), note


def finish(meta, body, packet):
    A.save_packet(packet, cfg)
    path, report = A.save_article(meta, body, packet, cfg)
    print(f"{path.name}: gate {report['gate']} · originality {report['originality_score']} · "
          f"quality {report['quality_score']} · overlap {report['source_overlap']:.0%}")
    for r in report["gate_reasons"]:
        print(f"   gate: {r}")
    for i in report["issues"]:
        print(f"   {i['level']}: {i['code']}: {i['detail'][:110]}")


# =============================================================== 1. BREAKING
p = A.load_packet("story-224-love-interview", cfg)
p["claims"] = [c for c in p["claims"] if c["kind"] == "headline"]
p["conflicts"] = []
vgc, poly = src(p, "VGC", "videogameschronicle"), src(p, "Polygon", "polygon.com")
gr, pcg = src(p, "GamesRadar+", "gamesradar.com"), src(p, "PC Gamer", "pcgamer.com")
ign = next(s["id"] for s in p["sources"] if s["publisher"] == "IGN Southeast Asia")
for sid in (vgc, poly, gr, pcg):
    opened(p, sid)
opened(p, ign, "Stored link is a Google News redirect; opened at https://sea.ign.com/grand-theft-auto-vi-rumored-title/"
               "249788/rockstar-traveled-across-florida-with-gang-members-and-cops-for-gta-6-research")
c = lambda *a, **k: A.add_claim(p, *a, **k)["id"]
v_who = c("VGC reports that Rupert Humphries, whom it describes as Rockstar's senior vice president of narrative, "
          "made the comments in a new issue of Love Magazine.", vgc,
          "VGC, 5 Oct 2026: Humphries 'made the comments in a new issue of Love Magazine'.")
v_pol = c("Humphries said earlier GTA games never focused much on national politics.", vgc, "Direct quote in VGC.",
          quote="If you go back to the previous GTAs, there's never really been much focus on national politics")
v_spec = c("Humphries said Rockstar does not want to be too specific about any person, event or movement.", vgc,
           "Direct quote in VGC.",
           quote="Because we are trying to make games that feel very specific to the moment they are released, but at the "
                 "same time, not reflective of the exact world we live in, we don't want to be too specific about any "
                 "particular person, event, movement, or anything like that.")
v_signs = c("Humphries said players will encounter election signs, receive robocalls from campaigns and hear commercials "
            "and political talk shows on the radio.", vgc, "Paraphrased by VGC, not a direct quote.")
v_mirror = c("Humphries said the aim is satire that is larger than life rather than a mirror.", vgc,
             "Direct quote in VGC; the same sentence is quoted by PC Gamer.",
             quote="There is a big focus on not just holding up a mirror, but on making everything satirical, larger than "
                   "life, and more grotesque.")
g_who = c("GamesRadar+ reports that Rob Nelson, whom it describes as co-studio head of Rockstar North, spoke in a new "
          "interview with Love magazine.", gr, "GamesRadar+, 5 Oct 2026.")
g_real = c("Nelson said realism helps immersion but too much can feel tedious.", gr, "Direct quote in GamesRadar+.",
           quote="Sometimes you need things to feel realistic to help with that sense of immersion, and conversely, "
                 "sometimes you need to forego realism in favor of what will be most convenient for the player – realism "
                 "can help greatly with immersion, but too much can feel tedious, so we try to find the right balance")
g_omit = c("Nelson said some aspects of reality are left out because they do not fit the experience.", gr,
           "Direct quote in GamesRadar+.",
           quote="sometimes it's better to ignore or omit certain aspects of reality because they just don't make sense "
                 "with the experience we are trying to create")
i_who = c("IGN reports comments by Aaron Garbut, whom it describes as head of development, on Rockstar's research trips.",
          ign, "IGN Southeast Asia, 5 Oct 2026, by Kirk McKeand.")
i_trip = c("Garbut said an early research trip ran from Miami through surrounding towns and the Florida Keys to Key West.",
           ign, "Direct quote in IGN.",
           quote="To begin, a small group of us spent some time traveling from Miami through some of the surrounding "
                 "towns and through the Florida Keys down to Key West.")
i_cops = c("Garbut said the team travels with police and with gang members during research.", ign, "Direct quote in IGN.",
           quote="We travel around with cops and with gang members.")
p_how = c("Polygon says parts of the Love Magazine interview and screenshots of it have been shared by fans online, and "
          "that issue 27 is out on 5 October.", poly, "Polygon, 5 Oct 2026, by Ashely Claudino.")
p_bg = c("James Horton, described by Polygon as writing director, said there is no background in the game.", poly,
         "Direct quote in Polygon.",
         quote="In a way, there's no 'background' in this game")
p_fg = c("Horton described background characters as foreground the player is not yet paying attention to.", poly,
         "Direct quote in Polygon.", quote="There's just foreground you're not paying attention to right now.")
p_dream = c("Polygon attributes a comment about a more modest American Dream to 'Robert Humphries, senior vice president "
            "of narrative'.", poly, "Direct quote in Polygon. Note the first name differs from VGC and PC Gamer.",
            quote="Maybe the American Dream is more modest now. It's a house for your family and your loans paid off "
                  "instead of wild success — but maybe today, that is just as out of reach for the average person.")
c_first = c("PC Gamer covered the same interview on 4 October, naming Rupert Humphries as senior vice president of "
            "narrative and Rob Nelson as head of development and co-studio head at Rockstar North.", pcg,
            "PC Gamer, 4 Oct 2026, by Jody Macgregor.")
c_writers = c("PC Gamer quotes game writer Elizabeth Gauvey-Kern on the two protagonists.", pcg, "Direct quote in PC Gamer.",
              quote="We wanted both protagonists to be vulnerable, tough, flawed, right sometimes, wrong sometimes, able "
                    "to learn from each other")
p["conflicts"] = [
    {"description": "First name of the senior vice president of narrative: VGC and PC Gamer say Rupert Humphries, "
                    "Polygon says Robert Humphries. Not checked against the magazine.", "resolved": False},
    {"description": "'Head of development' is given to Aaron Garbut by IGN and to Rob Nelson (with co-studio head) by "
                    "PC Gamer; GamesRadar+ calls Nelson co-studio head only.", "resolved": False}]

body1 = f"""Rockstar Games staff have given a long interview to Love Magazine about Grand Theft Auto VI, and five outlets have now reported different parts of it.[^{v_who}][^{g_who}][^{i_who}][^{p_how}][^{c_first}] None of them has published the interview in full, so what follows is assembled from those reports, with each line traced to the outlet that carried it.

*This article relies on reports of the interview. We have not read the magazine itself, which is why it is labelled a high-confidence report and not confirmed.*

## What was said

**On politics.** Rupert Humphries, described by VGC as Rockstar's senior vice president of narrative, said the series has rarely dealt with national politics: "If you go back to the previous GTAs, there's never really been much focus on national politics".[^{v_who}][^{v_pol}] He said the studio avoids naming real people, events or movements.[^{v_spec}] VGC adds that, by his account, players will still come across election signs, campaign robocalls and political talk radio.[^{v_signs}]

**On satire.** Humphries also described the tone: "There is a big focus on not just holding up a mirror, but on making everything satirical, larger than life, and more grotesque."[^{v_mirror}]

**On realism.** Rob Nelson, described by GamesRadar+ as co-studio head of Rockstar North, said realism is a tool and not the goal.[^{g_who}][^{g_real}] In his words, "sometimes it's better to ignore or omit certain aspects of reality because they just don't make sense with the experience we are trying to create".[^{g_omit}]

**On the world's characters.** James Horton, described by Polygon as writing director, said: "In a way, there's no 'background' in this game".[^{p_bg}] He went on: "There's just foreground you're not paying attention to right now."[^{p_fg}]

**On research.** Aaron Garbut, described by IGN as head of development, said an early trip ran from Miami through the Florida Keys to Key West.[^{i_who}][^{i_trip}] He also said: "We travel around with cops and with gang members."[^{i_cops}]

**On the protagonists.** PC Gamer quotes game writer Elizabeth Gauvey-Kern: "We wanted both protagonists to be vulnerable, tough, flawed, right sometimes, wrong sometimes, able to learn from each other".[^{c_writers}]

## Who reported what

| Speaker | Subject | Reported by |
|---|---|---|
| Humphries | Politics, satire | VGC[^{v_pol}], PC Gamer[^{c_first}] |
| Humphries | The American Dream | Polygon[^{p_dream}] |
| Rob Nelson | Realism and immersion | GamesRadar+[^{g_real}], PC Gamer[^{c_first}] |
| James Horton | Background characters | Polygon[^{p_bg}] |
| Aaron Garbut | Research trips | IGN[^{i_trip}] |
| Elizabeth Gauvey-Kern | Jason and Lucia | PC Gamer[^{c_writers}] |

## Where the reports disagree

The outlets do not agree on one name. VGC and PC Gamer call the senior vice president of narrative Rupert Humphries; Polygon calls him Robert Humphries.[^{v_who}][^{c_first}][^{p_dream}] Job titles differ as well: IGN gives head of development to Garbut, while PC Gamer gives that title, alongside co-studio head, to Nelson.[^{i_who}][^{c_first}]

Polygon notes that its account draws on parts of the interview and screenshots shared by fans online.[^{p_how}]

## Why it matters

Read together, the comments describe one design position from several directions. The game is meant to feel like the present without pinning itself to named people or passing trends, and its realism stops where it would become a chore. Those are choices about tone and pacing, and they are the kind of thing a trailer cannot show.

The headline phrase about a game with no background characters deserves care. In the quote as carried, it is a way of describing how much attention the writers gave to passers-by. It is not a description of a feature, and it should not be repeated as one.

## What we don't know

We do not know the full wording or order of the interview, because we have only seen what other outlets chose to quote. We also cannot settle the disputed first name or the job titles without the magazine in hand. Until then, treat every quotation above as a report of what was printed.
"""
meta1 = dict(story_id=p["story_id"], parent_event_id=p["parent_event_id"], angle_id=p["angle_id"],
             title="What Rockstar's developers told Love Magazine about GTA VI",
             slug="what-rockstar-told-love-magazine-about-gta-vi",
             description="Five outlets have relayed one Rockstar interview. Here is what was said about politics, realism, "
                         "NPCs and research, who said it, and where the reports differ.",
             hero_media=None, author=BYLINE, game="gta-vi", content_type="news", editorial_bucket="BREAKING", verification_status="HIGH_CONFIDENCE_REPORT",
             tags=["Rockstar Games", "interviews", "development", "satire"], related_content=[], status="DRAFT")
finish(meta1, body1, p)

# =============================================================== 2. EXPLAINER
p = A.load_packet("story-186-pegi-listing-explained", cfg)
p["claims"] = [c for c in p["claims"] if c["kind"] == "headline"]
p["sensitive"] = True      # sexual content and drug use: always goes to an editor
vgc, eg, pcg = src(p, "VGC", "videogameschronicle"), src(p, "Eurogamer", "pegi-lucia"), src(p, "PC Gamer", "pcgamer.com")
for sid in (vgc, eg, pcg):
    opened(p, sid)
c = lambda *a, **k: A.add_claim(p, *a, **k)["id"]
x_pub = c("VGC reports that Europe's PEGI board published an 18 rating for GTA 6 on a Friday with detailed content "
          "descriptions, and that the listing was quickly pulled from the board's website.", vgc,
          "VGC, 3 Oct 2026, by Andy Robinson.")
x_viol = c("The withdrawn listing described the violence as bloody and highly realistic.", vgc, "Quoted by VGC.",
           quote="bloody with a high degree of realism")
x_drug = c("The withdrawn listing said cocaine can be carried and used at any time.", vgc,
           "Quoted by VGC; Eurogamer and PC Gamer carry the same sentence.",
           quote="Most notably, cocaine can be carried around by the player and snorted directly from their hand at any time")
x_sex = c("The withdrawn listing listed nudity, intercourse and occasional sexual fetishes.", vgc, "Quoted by VGC.",
          quote="nudity, scenes of intercourse and occasional scenes of sexual fetishes")
x_animal = c("The listing said domestic animals can be harmed, with less injury detail than human characters.", vgc,
             "Paraphrased from VGC, which quotes the listing in part.")
x_esrb = c("VGC says the PEGI rating came days after an ESRB rating of M for Mature, and gives the release date as "
           "19 November.", vgc, "Stated in VGC's own words, not attributed to an official post in the article.")
e_fans = c("Eurogamer reports that the rating was uploaded and quickly deleted from PEGI's website, but not before fans "
           "saved and shared details from the listing.", eg, "Eurogamer, 2 Oct 2026, by Kaan Serin.")
e_gta5 = c("Eurogamer says GTA 5 and GTA Online include optional bongs that can normally only be found in player-owned "
           "apartments, not carried around the wider world.", eg, "Eurogamer's own comparison.")
e_sep = c("Eurogamer says a separate age rating earlier the same day suggested GTA 6 may be the first Grand Theft Auto "
          "to directly depict sex scenes.", eg, "Eurogamer; the separate rating is not identified in the passage read.")
g_sum = c("PC Gamer reports the rating summary as it appeared before deletion, crediting GamesRadar+ with spotting it.",
          pcg, "PC Gamer, 4 Oct 2026, by Rick Lane.",
          quote="features strong graphic violence, strong sexual themes, and use of illegal drugs")

body2 = f"""On a Friday in early October, Europe's games ratings board PEGI published an 18 rating for Grand Theft Auto VI together with an unusually specific description of its content, then removed the page.[^{x_pub}] The rating itself surprised nobody. The level of detail did, and so did the fact that it vanished.

*This article describes a ratings listing that was withdrawn. The quotations come from outlets that reported it before or after removal. We have not seen the original page.*

## What the listing said

According to PC Gamer, the summary stated that the game "features strong graphic violence, strong sexual themes, and use of illegal drugs".[^{g_sum}] The detail underneath is what drew attention:

- **Violence.** VGC quotes the listing as describing it as "bloody with a high degree of realism".[^{x_viol}]
- **Drugs.** The listing reportedly read: "Most notably, cocaine can be carried around by the player and snorted directly from their hand at any time".[^{x_drug}]
- **Sexual content.** It listed "nudity, scenes of intercourse and occasional scenes of sexual fetishes".[^{x_sex}]
- **Animals.** VGC says the listing noted that domestic animals can be harmed, with less injury detail than for human characters.[^{x_animal}]

## How we know what it said

This is the part most coverage skips. Eurogamer reports that the page was uploaded and quickly deleted, but not before fans saved and shared details from it.[^{e_fans}] PC Gamer credits another outlet with spotting the text.[^{g_sum}] In other words, the wording now in circulation reached readers through copies, not through a page anyone can open today.

| What is reported | Who reports it |
|---|---|
| An 18 rating was published and then pulled | VGC[^{x_pub}], Eurogamer[^{e_fans}] |
| The summary wording | PC Gamer[^{g_sum}] |
| The drug-use sentence | VGC[^{x_drug}] |
| The sexual-content wording | VGC[^{x_sex}] |

## How it compares

Eurogamer draws the comparison with the previous game: GTA 5 and GTA Online include optional bongs, but they can normally only be found in player-owned apartments and are not carried around the wider world.[^{e_gta5}] If the withdrawn listing is accurate, drug use that travels with the player would be a change of degree. Eurogamer also says a separate rating published earlier the same day pointed to directly depicted sex scenes.[^{e_sep}]

VGC places the listing in sequence: it says the PEGI rating followed an ESRB rating of M for Mature, and gives the release date as 19 November.[^{x_esrb}]

## What we don't know

A ratings description tells you what a board saw and chose to describe. It does not tell you how often something appears, whether it is optional, or how it plays. Nothing in the listing explains whether drug use has any effect on the character, for example, and it would be a mistake to read a mechanic into one sentence.

We also do not know why the page was removed. A withdrawn page could mean the text was published early, published in error, or simply due for revision, and nothing we have read settles which. The safest reading is the narrow one: a board assessed the game as suitable for adults and briefly gave its reasons.

## Why it matters

Ratings text is one of the few places where a game's content is described by someone other than its publisher or the press. That makes it useful, and it is also why a withdrawn listing should be handled as a report of a document, not as the document.
"""
meta2 = dict(story_id=p["story_id"], parent_event_id=None, angle_id=p["angle_id"],
             title="GTA VI's withdrawn PEGI listing: what it said and what it doesn't prove",
             slug="gta-vi-withdrawn-pegi-listing-explained",
             description="Europe's ratings board briefly published an 18 rating for GTA VI with unusually specific detail. "
                         "What it said, how we know, and the limits of reading it.",
             hero_media=None, author=BYLINE, game="gta-vi", content_type="explainer", editorial_bucket="EXPLAINER", verification_status="CREDIBLE_RUMOUR",
             tags=["age ratings", "PEGI", "content"], related_content=[], status="DRAFT")
finish(meta2, body2, p)

# =============================================================== 3. EVERGREEN
p = A.load_packet("story-90-evergreen-rockstar-history", cfg)
p["claims"] = [c for c in p["claims"] if c["kind"] == "headline"]
vh = next(s["id"] for s in p["sources"] if s["publisher"] == "VGC" and "dan-houser" in s["url"])
vgc, poly = src(p, "VGC", "political-references"), src(p, "Polygon", "polygon.com")
gr, pcg = src(p, "GamesRadar+", "forego-realism"), src(p, "PC Gamer", "pcgamer.com")
ign = next(s["id"] for s in p["sources"] if s["publisher"] == "IGN Southeast Asia")
for sid in (vh, vgc, poly, gr, pcg):
    opened(p, sid)
opened(p, ign, "Stored link is a Google News redirect; opened at sea.ign.com (article id 249788).")
c = lambda *a, **k: A.add_claim(p, *a, **k)["id"]
h_role = c("VGC describes Rupert Humphries as Rockstar's senior vice president of narrative and reports his comments on "
           "political satire from Love Magazine.", vgc, "VGC, 5 Oct 2026.")
h_alt = c("Polygon names the senior vice president of narrative as Robert Humphries.", poly, "Polygon, 5 Oct 2026.")
n_role = c("GamesRadar+ describes Rob Nelson as co-studio head of Rockstar North and reports his comments on realism "
           "and immersion.", gr, "GamesRadar+, 5 Oct 2026.")
n_alt = c("PC Gamer describes Rob Nelson as head of development and co-studio head at Rockstar North.", pcg,
          "PC Gamer, 4 Oct 2026.")
g_role = c("IGN describes Aaron Garbut as head of development and reports his account of research trips in Florida.",
           ign, "IGN Southeast Asia, 5 Oct 2026.")
o_role = c("Polygon describes James Horton as writing director; PC Gamer gives the fuller title 'writing director: open "
           "world'.", poly, "Polygon, 5 Oct 2026; title variant from PC Gamer, 4 Oct 2026.")
o_alt = c("PC Gamer gives James Horton's title as writing director: open world and reports his comments on overheard "
          "conversations in the city.", pcg, "PC Gamer, 4 Oct 2026.")
w_role = c("PC Gamer describes Elizabeth Gauvey-Kern and Alexa D'Agostino as game writers and quotes both on the "
           "protagonists.", pcg, "PC Gamer, 4 Oct 2026.")
d_role = c("VGC describes Dan Houser as a Rockstar co-founder who wrote and produced Grand Theft Auto 3 to 5, Red Dead "
           "Redemption 1 and 2, Bully and Max Payne 3, and who left Rockstar in 2020 to found Absurd Ventures.", vh,
           "VGC, 3 Oct 2026, by Andy Robinson.")
d_seen = c("Dan Houser told Variety he has not seen GTA 6 and tries to avoid it.", vh, "Direct quote in VGC.",
           quote="I haven't seen it yet. I will try and avoid it because I always try and avoid stuff that's going to "
                 "distract or disrupt me creatively")
d_sam = c("VGC says Rockstar is helmed by Dan Houser's brother, Sam.", vh, "VGC, 3 Oct 2026.")
d_next = c("VGC says Absurd Ventures is working on two open-world games, one a comedy action-adventure.", vh,
           "VGC, 3 Oct 2026, attributed to Houser.")

body3 = f"""Several named Rockstar people have now spoken on the record about Grand Theft Auto VI, and a former one has explained why he is staying away from it. This page keeps track of who they are, how each has been described, and what each has been reported as saying.[^{h_role}][^{n_role}][^{g_role}][^{d_role}]

*This is a reference page. Roles are given as the cited outlet printed them, and we note where outlets differ. It is updated when the record changes.*

## The people

| Name | Role as reported | Has spoken about | Source |
|---|---|---|---|
| Rupert Humphries | Senior vice president of narrative | Political satire and tone | VGC[^{h_role}] |
| Rob Nelson | Co-studio head of Rockstar North | Realism and immersion | GamesRadar+[^{n_role}] |
| Aaron Garbut | Head of development | Research trips in Florida | IGN[^{g_role}] |
| James Horton | Writing director | The world's characters | Polygon[^{o_role}] |
| Elizabeth Gauvey-Kern | Game writer | The protagonists | PC Gamer[^{w_role}] |
| Alexa D'Agostino | Game writer | The protagonists | PC Gamer[^{w_role}] |
| Dan Houser | Co-founder, left in 2020 | Why he avoids the game | VGC[^{d_role}] |

## Inside the studio

**Rupert Humphries** is the voice on writing and tone. VGC reports his comments on how the game handles political satire.[^{h_role}]

**Rob Nelson** has spoken about design trade-offs, in particular where realism helps and where it gets in the way.[^{n_role}]

**Aaron Garbut** has described how the studio researches a setting, including time spent travelling in Florida.[^{g_role}]

**James Horton** has talked about the people who fill the world, and PC Gamer reports his remarks on the conversations a player overhears in the city.[^{o_role}][^{o_alt}]

**Elizabeth Gauvey-Kern and Alexa D'Agostino** are credited as game writers and are quoted on how Jason and Lucia were written.[^{w_role}]

See also: [What Rockstar's developers told Love Magazine about GTA VI](/articles/what-rockstar-told-love-magazine-about-gta-vi/).

## Outside the studio

**Dan Houser** co-founded Rockstar and, by VGC's account, wrote and produced much of its best-known work before leaving in 2020 to found Absurd Ventures.[^{d_role}] He told Variety: "I haven't seen it yet. I will try and avoid it because I always try and avoid stuff that's going to distract or disrupt me creatively".[^{d_seen}] VGC adds that Rockstar is now led by his brother, Sam, and that Absurd Ventures has two open-world games in development.[^{d_sam}][^{d_next}]

## Where the reports disagree

- **A first name.** VGC gives Rupert Humphries; Polygon gives Robert Humphries for the same role.[^{h_role}][^{h_alt}]
- **A job title.** IGN gives head of development to Aaron Garbut; PC Gamer gives head of development and co-studio head to Rob Nelson; GamesRadar+ gives Nelson co-studio head only.[^{g_role}][^{n_alt}][^{n_role}]
- **A fuller title.** Polygon calls James Horton writing director; PC Gamer adds that the role covers the open world.[^{o_role}][^{o_alt}]

## Context

It is unusual for this many people from one studio to be quoted by name about a single game before release, and the spread of roles is informative in itself. Narrative, development, world writing and character writing are each represented, which suggests the studio wanted the game described from several desks at once.

The disagreements above are small, but they are a reminder that a name or title copied from one article can be wrong. Where it matters, check the original.

## What we don't know

We have not seen an official staff list, so every role here is as an outlet printed it. We also do not know who else was interviewed but not quoted. This page lists only people an outlet has named and tied to a specific statement.
"""
meta3 = dict(story_id=p["story_id"], parent_event_id=p["parent_event_id"], angle_id=p["angle_id"],
             title="Who is speaking for GTA VI: Rockstar's named voices and their roles",
             slug="who-is-speaking-for-gta-vi-rockstar-voices",
             description="A reference list of the Rockstar people quoted about GTA VI so far: their roles as reported, what "
                         "each has spoken about, and where the reports disagree.",
             hero_media=None, author=BYLINE, game="gta-vi", content_type="guide", editorial_bucket="EVERGREEN", verification_status="HIGH_CONFIDENCE_REPORT",
             tags=["Rockstar Games", "Rockstar interviews", "people", "reference", "development"],
             related_content=["what-rockstar-told-love-magazine-about-gta-vi"], status="DRAFT")
p["conflicts"] = [{"description": "First name of the senior vice president of narrative (Rupert in VGC and PC Gamer, "
                                  "Robert in Polygon) is unresolved; the article reports both.", "resolved": False}]
finish(meta3, body3, p)
