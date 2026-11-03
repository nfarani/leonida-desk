-- GTA VI content intelligence: SQLite schema v1
PRAGMA foreign_keys = ON;

-- Publishers / feeds that items come from
CREATE TABLE IF NOT EXISTS sources (
  id            INTEGER PRIMARY KEY,
  name          TEXT NOT NULL,
  domain        TEXT NOT NULL UNIQUE,
  source_type   TEXT NOT NULL CHECK (source_type IN ('primary','journalism','community','demand')),
  tier          INTEGER NOT NULL DEFAULT 3,      -- 0 official, 1 top journalism ... 4 community
  created_at    TEXT NOT NULL
);

-- Editorial themes (category + topic). Used for topic cooldown & saturation tracking.
CREATE TABLE IF NOT EXISTS content_clusters (
  id            INTEGER PRIMARY KEY,
  slug          TEXT NOT NULL UNIQUE,            -- e.g. 'trailer_discoveries'
  label         TEXT NOT NULL,
  last_used_at  TEXT,                            -- last time content in this cluster was published
  created_at    TEXT NOT NULL
);

-- One row per UNDERLYING story (deduplicated event)
CREATE TABLE IF NOT EXISTS stories (
  id                  INTEGER PRIMARY KEY,
  headline            TEXT NOT NULL,
  summary             TEXT,
  source_url          TEXT NOT NULL,             -- best (most authoritative) source
  source_name         TEXT NOT NULL,
  source_type         TEXT NOT NULL,
  published_at        TEXT,                      -- earliest known publication of the event
  first_seen_at       TEXT NOT NULL,             -- when THIS system first discovered it
  last_updated_at     TEXT NOT NULL,             -- last time a new source item attached
  last_material_update_at TEXT,                  -- last update that counts as a "meaningful new development"
  verification_status TEXT NOT NULL CHECK (verification_status IN
      ('CONFIRMED','HIGH_CONFIDENCE_REPORT','CREDIBLE_RUMOUR','COMMUNITY_DISCOVERY',
       'THEORY','SPECULATION','FALSE_OR_DEBUNKED')),
  content_cluster     TEXT REFERENCES content_clusters(slug),
  freshness_score     REAL,                      -- 0-1
  viral_score         REAL,                      -- 0-100
  saturation_score    REAL,                      -- 0-100 (higher = more crowded)
  opportunity_score   REAL,                      -- 0-100 weighted
  score_breakdown     TEXT,                      -- JSON per-dimension
  reasoning           TEXT,
  status              TEXT NOT NULL DEFAULT 'new' CHECK (status IN
      ('new','recommended','used','rejected','stale')),
  used_at             TEXT,
  fingerprint         TEXT                       -- normalised token signature for dedup
);
CREATE INDEX IF NOT EXISTS idx_stories_seen ON stories(first_seen_at);
CREATE INDEX IF NOT EXISTS idx_stories_status ON stories(status);

-- Every individual article/post/video attached to a story
CREATE TABLE IF NOT EXISTS story_sources (
  id            INTEGER PRIMARY KEY,
  story_id      INTEGER NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
  source_id     INTEGER REFERENCES sources(id),
  url           TEXT NOT NULL UNIQUE,
  title         TEXT NOT NULL,
  snippet       TEXT,
  publisher     TEXT,
  source_type   TEXT NOT NULL,
  tier          INTEGER NOT NULL,
  discovered_via TEXT,                           -- feed id or 'web_search'
  published_at  TEXT,
  fetched_at    TEXT NOT NULL,
  engagement    TEXT                             -- JSON {score, comments, views}
);
CREATE INDEX IF NOT EXISTS idx_ss_story ON story_sources(story_id);

-- Each /morning run
CREATE TABLE IF NOT EXISTS runs (
  id            INTEGER PRIMARY KEY,
  started_at    TEXT NOT NULL,
  finished_at   TEXT,
  stats         TEXT,                            -- JSON: feeds ok/failed, items, stories
  report_path   TEXT
);

CREATE TABLE IF NOT EXISTS recommendations (
  id                INTEGER PRIMARY KEY,
  run_id            INTEGER NOT NULL REFERENCES runs(id),
  story_id          INTEGER NOT NULL REFERENCES stories(id),
  rank              INTEGER NOT NULL,
  opportunity_score REAL NOT NULL,
  rank_score        REAL NOT NULL,
  post_now          INTEGER NOT NULL DEFAULT 0,
  why_care          TEXT,
  recommended_format TEXT,
  recommended_angle TEXT,
  suggested_hook    TEXT,
  risk_caveat       TEXT,
  created_at        TEXT NOT NULL,
  editorial_bucket  TEXT,                        -- BREAKING | DISCOVERY | EXPLAINER | EVERGREEN
  recommended_output TEXT                        -- VIDEO_ONLY | ARTICLE_ONLY | VIDEO_AND_ARTICLE
);

-- Filled when the Editor-in-Chief publishes something (scripts/mark_used.py for now)
CREATE TABLE IF NOT EXISTS published_content (
  id                INTEGER PRIMARY KEY,
  story_id          INTEGER NOT NULL REFERENCES stories(id),
  recommendation_id INTEGER REFERENCES recommendations(id),
  platform          TEXT NOT NULL CHECK (platform IN ('youtube','youtube_shorts','tiktok','instagram','other')),
  url               TEXT,
  title             TEXT,
  format            TEXT,
  published_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS performance_metrics (
  id                   INTEGER PRIMARY KEY,
  published_content_id INTEGER NOT NULL REFERENCES published_content(id),
  captured_at          TEXT NOT NULL,
  views                INTEGER, likes INTEGER, comments INTEGER, shares INTEGER, saves INTEGER,
  avg_view_duration_s  REAL, retention_pct REAL, followers_gained INTEGER
);

-- ============================================================ audience (prepared; mostly unused)
-- Newsletter sign-ups captured by a first-party endpoint. With a hosted provider the provider is
-- the system of record and this table stays empty.
CREATE TABLE IF NOT EXISTS newsletter_subscribers (
  id               INTEGER PRIMARY KEY,
  email            TEXT NOT NULL UNIQUE,
  consent_at       TEXT NOT NULL,                -- when the reader ticked the consent box
  signup_source    TEXT,                         -- homepage | article:<slug> | newsletter-page | game:<slug>
  preferred_games  TEXT,                         -- JSON list of game slugs
  topic_interests  TEXT,                         -- JSON list
  status           TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','confirmed','unsubscribed')),
  created_at       TEXT NOT NULL
);

-- Future accounts and community features. All behind feature flags that are off (config/flags.yaml).
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE, display_name TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS saved_articles (
  user_id INTEGER NOT NULL REFERENCES users(id), article_slug TEXT NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY (user_id, article_slug)
);
CREATE TABLE IF NOT EXISTS followed_games (
  user_id INTEGER NOT NULL REFERENCES users(id), game_slug TEXT NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY (user_id, game_slug)
);
CREATE TABLE IF NOT EXISTS comments (
  id INTEGER PRIMARY KEY, article_slug TEXT NOT NULL, user_id INTEGER NOT NULL REFERENCES users(id),
  parent_id INTEGER REFERENCES comments(id),     -- threading
  body TEXT NOT NULL, created_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','visible','hidden','spam')),
  reports INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS reactions (
  user_id INTEGER NOT NULL REFERENCES users(id), target_type TEXT NOT NULL, target_id TEXT NOT NULL,
  kind TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY (user_id, target_type, target_id)
);
CREATE TABLE IF NOT EXISTS notification_preferences (
  user_id INTEGER PRIMARY KEY REFERENCES users(id), email_news INTEGER DEFAULT 0, email_games INTEGER DEFAULT 0
);

-- ============================================================ video performance (simple loop)
-- One row per platform post of a video package. The descriptive columns are copied from the package
-- at publish time so the 10-video review can group by them.
CREATE TABLE IF NOT EXISTS video_posts (
  id            INTEGER PRIMARY KEY,
  video_id      TEXT NOT NULL,                   -- outputs/videos/<video_id>
  story_id      INTEGER REFERENCES stories(id),
  platform      TEXT NOT NULL CHECK (platform IN ('youtube_shorts','tiktok','instagram','youtube','other')),
  url           TEXT,
  published_at  TEXT NOT NULL,
  game          TEXT, topic TEXT, treatment TEXT, hook_style TEXT, visual_style TEXT,
  seconds       REAL,
  UNIQUE (video_id, platform)
);
-- Measured numbers only, entered by the editor from the platform's own analytics. `checkpoint`
-- is 1h, 24h, 7d or latest, so "views after 24h" is the row with checkpoint 24h.
CREATE TABLE IF NOT EXISTS video_metrics (
  id            INTEGER PRIMARY KEY,
  post_id       INTEGER NOT NULL REFERENCES video_posts(id),
  checkpoint    TEXT NOT NULL CHECK (checkpoint IN ('1h','24h','7d','latest')),
  captured_at   TEXT NOT NULL,
  views INTEGER, likes INTEGER, comments INTEGER, shares INTEGER,
  watch_time_s REAL, avg_pct_viewed REAL, completion_rate REAL, followers_gained INTEGER,
  UNIQUE (post_id, checkpoint)
);

-- ============================================================ editorial calibration
-- The operator's own rating of a candidate, with the scores the system gave it at that moment.
CREATE TABLE IF NOT EXISTS story_ratings (
  id         INTEGER PRIMARY KEY,
  story_id   INTEGER NOT NULL REFERENCES stories(id),
  rating     TEXT NOT NULL CHECK (rating IN ('GREAT','GOOD','MEDIOCRE','BAD')),
  note       TEXT,
  scores     TEXT NOT NULL,                      -- JSON snapshot: opportunity, viral, video, hook, visual, confidence, tier
  rated_at   TEXT NOT NULL
);
