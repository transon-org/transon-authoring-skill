"""Example-corpus retrieval over the pinned snapshot (FR-010, SPEC §7).

The authoritative example JSON is ``docs.examples`` inside the bundled
metadata snapshot (flat corpus of ``{name, doc, template, data, result,
tags}`` items, engine metadata_version 3.0). Freshly authored NL intents live
in the ``resources/nl-intents.json`` sidecar, keyed by stable example
``name``. ``search_examples`` implements the minimal normative contract of
resolved OQ-022 (ROADMAP §15; AC-022):

(a) an exact case-sensitive ``name`` match is always in the results, first;
(b) at most ``limit`` results (``limit >= 1``, default 10);
(c) determinism — a pure function of (query, snapshot, sidecar); ties and
    everything below the exact-name hit follow corpus order;
(d) each hit is the snapshot example object verbatim (deep-copied so callers
    cannot mutate the cached snapshot), plus an ``"nl"`` string copied from
    the sidecar when present — the sidecar enriches display only.

Ranking beyond (a)-(c) is non-normative. Concretely: the query is lowercased
and tokenized on whitespace; each example's searchable text is its ``name``,
``tags``, ``doc``, and sidecar ``nl`` (when present), lowercased and joined;
the score is the number of distinct query tokens occurring as substrings of
that text; score 0 is excluded; order is the exact-name hit first, then
descending score, ties by corpus index.
"""

from __future__ import annotations

import copy
import json

from .metadata import _resource_bytes, get_metadata

_SIDECAR_NAME = "nl-intents.json"


def _load_sidecar() -> dict:
    """Return the NL-intent sidecar's ``intents`` mapping (FR-010).

    Parsed fresh from the bundled ``resources/nl-intents.json`` — entries are
    ``{"<example-name>": {"nl": str, "notes"?: str}}``. Sidecar/ snapshot
    consistency is enforced by ``scripts/check_snapshot.py`` (OQ-021).
    """
    payload = json.loads(_resource_bytes(_SIDECAR_NAME).decode("utf-8"))
    intents = payload.get("intents")
    return intents if isinstance(intents, dict) else {}


def _sidecar_nl(intents: dict, name: str) -> str | None:
    """The sidecar ``nl`` string for example *name*, or ``None``."""
    entry = intents.get(name)
    if isinstance(entry, dict) and isinstance(entry.get("nl"), str):
        return entry["nl"]
    return None


def search_examples(query: str, *, limit: int = 10) -> list:
    """Search the snapshot ``docs.examples`` corpus (FR-010; OQ-022; AC-022).

    Returns at most *limit* hits; each hit is a deep copy of the snapshot
    example object, plus an ``"nl"`` key copied from the NL sidecar when that
    example has a sidecar entry. ``limit < 1`` raises ``ValueError``.
    """
    if limit < 1:
        raise ValueError(f"limit must be >= 1, got {limit}")

    corpus = get_metadata()["docs"]["examples"]
    intents = _load_sidecar()
    tokens = set(query.lower().split())

    exact_index: int | None = None
    scored: list[tuple[int, int]] = []  # (score, corpus index), corpus order
    for index, example in enumerate(corpus):
        if exact_index is None and example["name"] == query:
            exact_index = index  # OQ-022 (a): always in results, first.
            continue
        nl = _sidecar_nl(intents, example["name"])
        parts = [example["name"], *example["tags"], example["doc"]]
        if nl is not None:
            parts.append(nl)
        text = " ".join(parts).lower()
        score = sum(1 for token in tokens if token in text)
        if score > 0:
            scored.append((score, index))

    # OQ-022 (c): descending score, ties by corpus index (sort is stable and
    # `scored` is already in corpus order).
    scored.sort(key=lambda item: -item[0])
    ordered = [] if exact_index is None else [exact_index]
    ordered.extend(index for _, index in scored)

    hits = []
    for index in ordered[:limit]:
        hit = copy.deepcopy(corpus[index])  # OQ-022 (d): verbatim, unshared.
        nl = _sidecar_nl(intents, hit["name"])
        if nl is not None:
            hit["nl"] = nl
        hits.append(hit)
    return hits
