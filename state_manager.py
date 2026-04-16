"""
State Management Module — Report Section 2.3.

Every agent keeps a local state repository: a dictionary mapping data keys
(e.g., "temperature", "humidity") to StateEntry objects. This module handles
the merge logic when an agent receives new state from a gossip exchange.

The merge process:
  1. Iterate over each key in the incoming state.
  2. If the key is new (not in local state), accept it immediately.
  3. If the key exists locally, delegate to the ConflictResolver.
  4. Track what changed so the logger can report exactly what was learned.

This is also where the Knowledge Propagation Engine logic (Section 2.7)
lives in our implementation. The "is this new?" check during merge is the
core of propagation intelligence — we only update local state (and thus
only propagate further) when incoming data is genuinely newer.
"""

from __future__ import annotations

from conflict_resolver import ConflictResolver, StateEntry
from gossip_logger import EventType, GossipLogger


class StateManager:
    """
    Manages an agent's local knowledge repository.

    Provides merge operations for incoming gossip state and tracks
    what the agent knows vs. what's new.
    """

    def __init__(self, agent_id: str, logger: GossipLogger):
        self.agent_id = agent_id
        self._state: dict[str, StateEntry] = {}
        self._logger = logger
        self._resolver = ConflictResolver()

    @property
    def state(self) -> dict[str, StateEntry]:
        return dict(self._state)

    @property
    def known_keys(self) -> set[str]:
        return set(self._state.keys())

    def set_local(self, entry: StateEntry) -> None:
        """Set a value that this agent owns (e.g., its own sensor reading)."""
        self._state[entry.key] = entry

    def merge_incoming(
        self,
        incoming_state: dict[str, StateEntry],
        sender_id: str,
        round_number: int,
    ) -> list[str]:
        """
        Merge state received from a gossip peer.

        Returns the list of keys that were actually updated (new or newer).
        This return value is what the logger uses to show exactly which
        data an agent learned from a given exchange.
        """
        updated_keys: list[str] = []

        for key, incoming_entry in incoming_state.items():
            local_entry = self._state.get(key)

            winner, incoming_won = self._resolver.resolve(
                local_entry=local_entry,
                incoming_entry=incoming_entry,
                logger=self._logger,
                round_number=round_number,
                agent_id=self.agent_id,
            )

            if incoming_won:
                self._state[key] = winner
                updated_keys.append(key)

        if updated_keys:
            self._logger.log(
                EventType.STATE_MERGE,
                round_number=round_number,
                agent_id=self.agent_id,
                message=(
                    f"Merged {len(updated_keys)} new entries from {sender_id}: "
                    f"{updated_keys} | Now knows {len(self._state)} keys"
                ),
                data={
                    "sender": sender_id,
                    "updated_keys": updated_keys,
                    "total_keys": len(self._state),
                    "current_state": {k: v.to_dict() for k, v in self._state.items()},
                },
            )
        else:
            self._logger.log(
                EventType.STATE_NO_CHANGE,
                round_number=round_number,
                agent_id=self.agent_id,
                message=f"Nothing new from {sender_id} (already up to date)",
                data={"sender": sender_id, "total_keys": len(self._state)},
            )

        return updated_keys

    def get_state_snapshot(self) -> dict[str, dict]:
        """Return a serializable snapshot of current state for logging."""
        return {k: v.to_dict() for k, v in self._state.items()}
