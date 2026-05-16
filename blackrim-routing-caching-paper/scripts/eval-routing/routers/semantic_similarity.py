"""Semantic-similarity router using sentence-transformers.

Algorithm
---------
1. At construction, load all labelled exemplars from labels.yml (skip
   ``ambiguous`` turns).  For each exemplar, concatenate the turn's
   ``user_prompt`` and ``observed_response_summary`` and encode with the
   chosen sentence-transformers model.

2. At route time, encode the query turn the same way and compute cosine
   similarity against every exemplar embedding.

3. Return the majority-vote tier of the top-k exemplars (default k=5).

4. Conservative-escalation escape hatch: if the maximum cosine similarity
   across *all* exemplars is below ``min_similarity`` (default 0.30), return
   "opus" — the turn is likely out-of-distribution and the safer call is to
   use the most capable model.

Leave-one-out CV
----------------
Instantiate with ``loo_turn_id`` set to the turn being evaluated; that turn
is excluded from the exemplar set so it cannot cheat.  ``run.py`` drives this
via the ``--cv-loo`` flag.

Dependencies
------------
    pip install sentence-transformers

The default model (``all-MiniLM-L6-v2``) is ~80 MB and runs on CPU.
Swap via the ``model_name`` constructor argument or the
``SEMANTIC_ROUTER_MODEL`` environment variable.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    pass

_DEFAULT_MODEL = os.environ.get("SEMANTIC_ROUTER_MODEL", "all-MiniLM-L6-v2")
_DEFAULT_K = 5
_DEFAULT_MIN_SIM = 0.30

TIERS = ["haiku", "sonnet", "opus"]


def _load_exemplars(labels_path: Path, loo_turn_id: str | None = None) -> list[dict]:
    """Load exemplar records from labels.yml.

    Each record has keys: turn_id, tier, rationale.
    Ambiguous turns and (in LOO mode) the held-out turn are excluded.
    """
    with labels_path.open() as f:
        data = yaml.safe_load(f)

    exemplars = []
    for entry in data["labels"]:
        if entry["should_be_tier"] == "ambiguous":
            continue
        if loo_turn_id is not None and entry["turn_id"] == loo_turn_id:
            continue
        exemplars.append(
            {
                "turn_id": entry["turn_id"],
                "tier": entry["should_be_tier"],
                "rationale": entry.get("rationale", ""),
            }
        )
    return exemplars


def _turn_text(turn: dict) -> str:
    """Concatenate user_prompt and observed_response_summary for encoding."""
    prompt = turn.get("user_prompt", "")
    summary = turn.get("observed_response_summary", "") or ""
    return f"{prompt} {summary}".strip()


class SemanticSimilarityRouter:
    """k-NN router over exemplar embeddings with conservative escalation.

    Parameters
    ----------
    labels_path:
        Path to ``labels.yml``.
    turns_dir:
        Directory containing ``turn-NN.json`` files (needed to encode
        exemplar turns at load time).
    model_name:
        Sentence-transformers model identifier.  Default: all-MiniLM-L6-v2.
    k:
        Number of nearest neighbours for majority vote.
    min_similarity:
        Cosine-similarity floor; turns below this threshold are escalated
        to opus unconditionally.
    loo_turn_id:
        When set, this turn is excluded from the exemplar set (leave-one-out
        cross-validation).
    """

    name = "semantic-similarity"

    def __init__(
        self,
        labels_path: Path,
        turns_dir: Path,
        model_name: str = _DEFAULT_MODEL,
        k: int = _DEFAULT_K,
        min_similarity: float = _DEFAULT_MIN_SIM,
        loo_turn_id: str | None = None,
    ) -> None:
        from sentence_transformers import SentenceTransformer
        import numpy as np

        self._k = k
        self._min_similarity = min_similarity
        self._np = np

        # Load exemplar metadata (excluding ambiguous + LOO turn)
        exemplars = _load_exemplars(labels_path, loo_turn_id=loo_turn_id)

        # Load the actual turn JSON for each exemplar so we can encode it
        self._exemplar_tiers: list[str] = []
        texts: list[str] = []
        for ex in exemplars:
            turn_file = turns_dir / f"{ex['turn_id']}.json"
            if turn_file.exists():
                import json
                with turn_file.open() as f:
                    turn_data = json.load(f)
                texts.append(_turn_text(turn_data))
            else:
                # Fallback: encode the rationale text if turn file missing
                texts.append(ex["rationale"])
            self._exemplar_tiers.append(ex["tier"])

        self._model = SentenceTransformer(model_name)
        # Encode all exemplars once at construction time
        self._exemplar_embeddings = self._model.encode(
            texts, convert_to_numpy=True, normalize_embeddings=True
        )

    def route(self, turn: dict) -> str:
        """Return predicted tier for *turn* via k-NN cosine similarity."""
        np = self._np
        query_text = _turn_text(turn)
        query_emb = self._model.encode(
            [query_text], convert_to_numpy=True, normalize_embeddings=True
        )[0]

        # Cosine similarity (embeddings are L2-normalised, so dot product == cosine)
        similarities = self._exemplar_embeddings @ query_emb

        max_sim = float(np.max(similarities))
        if max_sim < self._min_similarity:
            # Out-of-distribution — conservative escalation to opus
            return "opus"

        # Top-k neighbours by similarity
        top_k_indices = np.argsort(similarities)[-self._k:][::-1]
        top_k_tiers = [self._exemplar_tiers[i] for i in top_k_indices]

        # Majority vote; ties broken by tier precedence (opus > sonnet > haiku)
        counts = {tier: top_k_tiers.count(tier) for tier in TIERS}
        best_count = max(counts.values())
        # Among tiers with the best count, prefer the higher tier (more conservative)
        for tier in ["opus", "sonnet", "haiku"]:
            if counts[tier] == best_count:
                return tier

        return "opus"  # unreachable, but safe default
