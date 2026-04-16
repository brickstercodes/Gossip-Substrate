"""
Consistency and Conflict Resolution Module — Report Section 2.8.

In a gossip-based system, two agents can independently update the same data
key before they communicate. When their states eventually meet during a
gossip exchange, we need a deterministic rule to decide which value wins.

This module uses a "last-write-wins" (LWW) strategy with version numbers
as the primary tiebreaker and timestamps as the secondary. LWW is the
simplest conflict resolution approach that still guarantees eventual
consistency — all agents will converge to the same value regardless of
the order they receive updates.

Alternative strategies (not implemented but noted for completeness):
  - Vector clocks: track causal ordering across agents (more complex)
  - CRDTs: conflict-free replicated data types (overkill for this demo)
  - Application-level merge: domain-specific logic (e.g., averaging sensor values)
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gossip_logger import GossipLogger, EventType


@dataclass
class StateEntry:
    """
    A single piece of knowledge in an agent's local state.

    Each entry is a versioned, timestamped fact. The version increments
    every time the source agent updates the value. The timestamp breaks
    ties when two independent updates happen to produce the same version.
    """

    key: str
    value: float
    unit: str
    version: int
    timestamp: float
    source_agent: str

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "value": self.value,
            "unit": self.unit,
            "version": self.version,
            "timestamp": round(self.timestamp, 4),
            "source_agent": self.source_agent,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StateEntry":
        return cls(**data)


class ConflictResolver:
    """
    Resolves conflicting state entries using last-write-wins.

    Returns the winning entry and whether the incoming entry won
    (i.e., whether local state should be updated).
    """

    @staticmethod
    def resolve(
        local_entry: StateEntry | None,
        incoming_entry: StateEntry,
        logger: "GossipLogger | None" = None,
        round_number: int = -1,
        agent_id: str = "",
    ) -> tuple[StateEntry, bool]:
        """
        Compare a local entry against an incoming one.

        Returns (winning_entry, did_incoming_win).

        Resolution rules (applied in order):
          1. If no local entry exists, incoming wins (new knowledge).
          2. Higher version number wins (explicit update).
          3. If versions match, later timestamp wins (tiebreaker).
          4. If both match, keep local (stability preference).
        """
        if local_entry is None:
            return incoming_entry, True

        incoming_wins = False

        if incoming_entry.version > local_entry.version:
            incoming_wins = True
        elif incoming_entry.version == local_entry.version:
            if incoming_entry.timestamp > local_entry.timestamp:
                incoming_wins = True

        if incoming_wins and logger:
            # Only log when there's an actual conflict (both existed with different values)
            if local_entry.value != incoming_entry.value:
                from gossip_logger import EventType

                logger.log(
                    EventType.CONFLICT_RESOLVED,
                    round_number=round_number,
                    agent_id=agent_id,
                    message=(
                        f"Conflict on '{incoming_entry.key}': "
                        f"local v{local_entry.version}={local_entry.value}{local_entry.unit} "
                        f"vs incoming v{incoming_entry.version}={incoming_entry.value}{incoming_entry.unit} "
                        f"-> incoming wins (v{incoming_entry.version})"
                    ),
                    data={
                        "key": incoming_entry.key,
                        "local_version": local_entry.version,
                        "local_value": local_entry.value,
                        "incoming_version": incoming_entry.version,
                        "incoming_value": incoming_entry.value,
                        "reason": "higher_version" if incoming_entry.version > local_entry.version else "later_timestamp",
                    },
                )

        winner = incoming_entry if incoming_wins else local_entry
        return winner, incoming_wins
