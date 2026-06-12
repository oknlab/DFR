"""
ranking.py — Result fusion & community ranking. Pure Python core, optional Redis.

Layers, applied in order by unified_search:

  1. Reciprocal Rank Fusion (RRF) across many engines, weighted by per-engine
     trust. Rewards cross-engine agreement instead of arrival order.
  2. Wilson lower-bound community score from Boost/Bury votes (per query+url),
     with exponential time decay, replacing the exploitable `votes * 2.0` hack.
  3. A final blend that combines fusion rank with the community signal.
  4. Learned per-engine weights: engines whose results get boosted gain trust;
     buried ones lose it. Persisted to Redis, shared across workers.

The pure functions (RRF, Wilson, blend) take pre-computed inputs so they stay
synchronous and testable. Persistence/learning live in AsyncVoteStore +
EngineWeights, which use Redis when available and fall back to memory.
"""

from __future__ import annotations

import json
import math
import time
import urllib.parse
from typing import Optional

# ─── Tunable constants ──────────────────────────────────────────────────────

RRF_K = 60                      # standard RRF damping; larger = flatter
WILSON_Z = 1.96                 # 95% confidence
VOTE_HALF_LIFE_S = 14 * 86400   # community votes decay to half over ~14 days
COMMUNITY_WEIGHT = 0.35         # how much the community signal nudges fusion

# Learned-weight bounds & step. Weights drift within [MIN, MAX] from the
# hand-tuned defaults so a brigade can't drive an engine to 0 or infinity.
WEIGHT_MIN = 0.4
WEIGHT_MAX = 1.3
WEIGHT_STEP = 0.01              # per-vote nudge to the contributing engines
WEIGHTS_REDIS_KEY = "rank:engine_weights"

# Per-engine trust weights w_e. Hand-tuned starting point; learned over time
# from Boost/Bury agreement. connectnet/duckduckgo are the real web engines;
# the independent index is a small curated set, trusted for precision but not
# allowed to dominate breadth.
DEFAULT_ENGINE_WEIGHTS: dict[str, float] = {
    "connectnet": 1.0,
    "duckduckgo": 1.0,
    "bing": 0.9,
    "google_proxy": 0.85,
    "independent": 0.7,
}


# ─── URL canonicalization (shared dedup identity) ───────────────────────────

def canonical_url(url: str) -> str:
    """Stable identity for a result: scheme-less netloc + path + sorted query."""
    try:
        p = urllib.parse.urlparse(url)
    except Exception:
        return url
    netloc = p.netloc.replace("www.", "").lower()
    path = p.path.rstrip("/")
    if p.query:
        q = urllib.parse.parse_qsl(p.query, keep_blank_values=True)
        q.sort()
        return f"{netloc}{path}?{urllib.parse.urlencode(q)}"
    return f"{netloc}{path}"


def domain_of(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc.replace("www.", "").lower()
    except Exception:
        return url


# ─── 1: Reciprocal Rank Fusion with per-engine weights ──────────────────────

def reciprocal_rank_fusion(
    engine_results: dict[str, list[dict]],
    weights: Optional[dict[str, float]] = None,
    k: int = RRF_K,
    hide_promoted: bool = True,
) -> list[dict]:
    """Fuse ranked lists from multiple engines into one ranked list.

    Returns fused, de-duplicated results sorted by descending RRF score. Each
    carries: rrf_score, engines (contributing), agreement (# engines),
    best_rank, _ranks {engine: rank}, and the merged source fields.
    """
    weights = weights or DEFAULT_ENGINE_WEIGHTS
    fused: dict[str, dict] = {}

    for engine, results in engine_results.items():
        w = weights.get(engine, 0.8)
        rank = 0
        for r in results:
            if hide_promoted and r.get("promoted", False):
                continue
            url = r.get("url")
            if not url:
                continue
            rank += 1
            key = canonical_url(url)
            contribution = w / (k + rank)

            entry = fused.get(key)
            if entry is None:
                entry = {**r, "rrf_score": 0.0, "engines": [], "best_rank": rank, "_ranks": {}}
                fused[key] = entry
            else:
                if len(r.get("snippet", "")) > len(entry.get("snippet", "")):
                    entry["snippet"] = r["snippet"]
                for f in ("title", "thumbnail", "source_type", "source_name"):
                    if not entry.get(f) and r.get(f):
                        entry[f] = r[f]
                entry["best_rank"] = min(entry["best_rank"], rank)

            entry["rrf_score"] += contribution
            if engine not in entry["engines"]:
                entry["engines"].append(engine)
            entry["_ranks"][engine] = rank

    out = list(fused.values())
    for e in out:
        e["agreement"] = len(e["engines"])
    out.sort(key=lambda x: x["rrf_score"], reverse=True)
    return out


# ─── 2: Wilson-score community ranking ──────────────────────────────────────

def wilson_lower_bound(up: float, down: float, z: float = WILSON_Z) -> float:
    """Wilson score lower bound of a Bernoulli proportion, in [0, 1]."""
    n = up + down
    if n <= 0:
        return 0.0
    p_hat = up / n
    z2 = z * z
    denom = 1 + z2 / n
    centre = p_hat + z2 / (2 * n)
    margin = z * math.sqrt((p_hat * (1 - p_hat) + z2 / (4 * n)) / n)
    return max(0.0, (centre - margin) / denom)


def decay_weight(now: float, ts: float) -> float:
    lam = math.log(2) / VOTE_HALF_LIFE_S
    return math.exp(-lam * max(0.0, now - ts))


# ─── In-memory VoteStore (sync; used by tests & as fallback backend) ─────────

class VoteStore:
    """In-memory Boost/Bury ledger keyed by (query, canonical_url).

    Per-(query, url) scoping contains brigading. Each vote stores a timestamp
    (decay) and the engines that surfaced the URL (for weight learning).
    """

    def __init__(self) -> None:
        # key -> list of (timestamp, +1|-1, [engines])
        self._votes: dict[tuple[str, str], list[tuple[float, int, list[str]]]] = {}

    @staticmethod
    def _key(query: str, url: str) -> tuple[str, str]:
        return (query.strip().lower(), canonical_url(url))

    def add(self, query: str, url: str, value: int, engines: Optional[list[str]] = None) -> None:
        if value == 0:
            return
        self._votes.setdefault(self._key(query, url), []).append(
            (time.time(), 1 if value > 0 else -1, list(engines or []))
        )

    def decayed_counts(self, query: str, url: str, now: Optional[float] = None) -> tuple[float, float]:
        votes = self._votes.get(self._key(query, url))
        if not votes:
            return (0.0, 0.0)
        now = now or time.time()
        up = down = 0.0
        for ts, v, _ in votes:
            w = decay_weight(now, ts)
            if v > 0:
                up += w
            else:
                down += w
        return (up, down)

    def community_score(self, query: str, url: str, now: Optional[float] = None) -> float:
        up, down = self.decayed_counts(query, url, now)
        return wilson_lower_bound(up, down)


_default_store = VoteStore()


def get_vote_store() -> VoteStore:
    return _default_store


# ─── 3: Final blend (pure; takes pre-computed community scores) ─────────────

def apply_community_ranking(
    fused: list[dict],
    community_scores: Optional[dict[str, float]] = None,
    client_rankings: Optional[dict] = None,
    community_weight: float = COMMUNITY_WEIGHT,
) -> list[dict]:
    """Blend RRF score with community + client signals and re-sort.

    final = rrf_score * (1 + community_weight * community)
            + client nudge (per-domain, client-side, never stored)

    `community_scores` maps canonical_url -> wilson score (pre-fetched, possibly
    from Redis). `client_rankings` is the browser's {domain: int}, applied but
    never persisted (strict-privacy preserved).
    """
    if not fused:
        return fused
    community_scores = community_scores or {}
    max_rrf = max((e.get("rrf_score", 0) for e in fused), default=1.0) or 1.0

    for e in fused:
        url = e.get("url", "")
        community = community_scores.get(canonical_url(url), 0.0)
        e["community_score"] = round(community, 4)

        final = e.get("rrf_score", 0.0) * (1 + community_weight * community)
        if client_rankings:
            final += (client_rankings.get(domain_of(url), 0) / 10.0) * max_rrf
        e["score"] = round(final, 6)

    fused.sort(key=lambda x: x.get("score", 0), reverse=True)
    return fused


# ─── One-call convenience (sync path: uses in-memory store) ─────────────────

def fuse_and_rank(
    engine_results: dict[str, list[dict]],
    query: str,
    weights: Optional[dict[str, float]] = None,
    hide_promoted: bool = True,
    client_rankings: Optional[dict] = None,
    store: Optional[VoteStore] = None,
) -> list[dict]:
    """RRF-fuse, then blend using the in-memory store's community scores."""
    store = store or _default_store
    fused = reciprocal_rank_fusion(engine_results, weights=weights, hide_promoted=hide_promoted)
    community = {
        canonical_url(e["url"]): store.community_score(query, e["url"])
        for e in fused if e.get("url")
    }
    return apply_community_ranking(fused, community_scores=community, client_rankings=client_rankings)


# ─── (b) Learned per-engine weights, persisted to Redis ─────────────────────

class EngineWeights:
    """Per-engine trust weights that adapt from Boost/Bury agreement.

    A boost on a result nudges every engine that surfaced it UP; a bury nudges
    them DOWN. Weights are clamped to [WEIGHT_MIN, WEIGHT_MAX] and persisted to
    Redis so all workers share one learned state.
    """

    def __init__(self, redis_client=None) -> None:
        self._redis = redis_client
        self._weights: dict[str, float] = dict(DEFAULT_ENGINE_WEIGHTS)

    async def load(self) -> None:
        if not self._redis:
            return
        try:
            raw = await self._redis.get(WEIGHTS_REDIS_KEY)
            if raw:
                saved = json.loads(raw)
                # Merge so newly-added engines keep their default.
                self._weights = {**DEFAULT_ENGINE_WEIGHTS, **{k: float(v) for k, v in saved.items()}}
        except Exception:
            pass

    async def _save(self) -> None:
        if not self._redis:
            return
        try:
            await self._redis.set(WEIGHTS_REDIS_KEY, json.dumps(self._weights))
        except Exception:
            pass

    def current(self) -> dict[str, float]:
        return dict(self._weights)

    async def learn(self, engines: list[str], value: int) -> None:
        """Nudge contributing engines by +/- WEIGHT_STEP and persist."""
        if not engines or value == 0:
            return
        step = WEIGHT_STEP if value > 0 else -WEIGHT_STEP
        for e in engines:
            base = self._weights.get(e, DEFAULT_ENGINE_WEIGHTS.get(e, 0.8))
            self._weights[e] = max(WEIGHT_MIN, min(WEIGHT_MAX, base + step))
        await self._save()


# ─── (a) Async, Redis-persisted VoteStore ───────────────────────────────────

class AsyncVoteStore:
    """Redis-backed vote ledger; falls back to an in-memory VoteStore.

    Storage model (Redis): one list per (query, url) at key
    `rank:votes:{sha?}` — we store compact JSON triples [ts, v, engines].
    Reads decay on the fly. With no Redis client, delegates to memory.
    """

    VOTE_TTL_S = 60 * 86400  # prune ledgers after ~60 days of inactivity

    def __init__(self, redis_client=None) -> None:
        self._redis = redis_client
        self._mem = _default_store  # shared in-memory fallback

    @staticmethod
    def _rkey(query: str, url: str) -> str:
        q = query.strip().lower()
        return f"rank:votes:{q}|{canonical_url(url)}"

    async def add(self, query: str, url: str, value: int, engines: Optional[list[str]] = None) -> None:
        if value == 0:
            return
        v = 1 if value > 0 else -1
        triple = json.dumps([time.time(), v, list(engines or [])])
        if self._redis:
            try:
                key = self._rkey(query, url)
                await self._redis.rpush(key, triple)
                await self._redis.expire(key, self.VOTE_TTL_S)
                return
            except Exception:
                pass
        self._mem.add(query, url, v, engines)

    async def decayed_counts(self, query: str, url: str, now: Optional[float] = None) -> tuple[float, float]:
        now = now or time.time()
        if self._redis:
            try:
                raw = await self._redis.lrange(self._rkey(query, url), 0, -1)
                if raw is not None:
                    up = down = 0.0
                    for item in raw:
                        ts, v, _ = json.loads(item)
                        w = decay_weight(now, ts)
                        if v > 0:
                            up += w
                        else:
                            down += w
                    return (up, down)
            except Exception:
                pass
        return self._mem.decayed_counts(query, url, now)

    async def community_score(self, query: str, url: str, now: Optional[float] = None) -> float:
        up, down = await self.decayed_counts(query, url, now)
        return wilson_lower_bound(up, down)

    async def community_scores_for(self, query: str, urls: list[str]) -> dict[str, float]:
        """Batch community scores keyed by canonical_url for a result set."""
        out: dict[str, float] = {}
        for u in urls:
            if not u:
                continue
            out[canonical_url(u)] = await self.community_score(query, u)
        return out
