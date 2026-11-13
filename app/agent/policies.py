from __future__ import annotations

from app.planning.world import WorldSnapshot


class PolicyViolation(RuntimeError):
    pass


def require_fresh_world(
    world: WorldSnapshot,
) -> None:

    stale = [
        name
        for name, fresh in world.freshness.items()
        if not fresh
    ]

    if stale:
        raise PolicyViolation(
            "STALE_SOURCE:" + ",".join(stale)
        )


def assert_web_is_evidence_only() -> None:
    """
    External page content may produce structured WebFact
    objects, but it cannot directly authorize a
    state-changing tool call.
    """

    return None