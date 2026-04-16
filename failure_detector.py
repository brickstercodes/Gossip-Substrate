"""
Failure Detection Mechanism — Report Section 2.4.

In a decentralized system, no single node knows whether another node is
alive or dead. Failure detection works by tracking heartbeats: if an agent
hasn't been heard from (directly or via gossip) within a threshold number
of rounds, it's first marked SUSPECTED, then DEAD.

The SUSPECTED -> DEAD two-phase approach avoids false positives from
transient network issues. An agent might just be unlucky and not get
picked as a gossip target for a couple of rounds — that shouldn't
immediately flag it as dead.

Agent health status is itself gossip-able data. When Agent_A marks
Agent_D as DEAD, that fact propagates through gossip to all other agents,
ensuring the whole network eventually agrees on who's alive.
"""

from __future__ import annotations

from enum import Enum

from gossip_logger import EventType, GossipLogger


class AgentStatus(Enum):
    ALIVE = "ALIVE"
    SUSPECTED = "SUSPECTED"
    DEAD = "DEAD"


# How many rounds of silence before status transitions
SUSPECT_THRESHOLD = 5   # rounds without hearing from agent -> SUSPECTED
DEAD_THRESHOLD = 8      # rounds without hearing from agent -> DEAD


class FailureDetector:
    """
    Tracks heartbeats from other agents and infers their health status.

    Each agent runs its own FailureDetector instance. It records the last
    round in which it received any communication (direct gossip or gossiped
    heartbeat data) from each known agent.
    """

    def __init__(self, agent_id: str, logger: GossipLogger):
        self.agent_id = agent_id
        self._logger = logger

        # agent_id -> last round we heard from them
        self._last_seen: dict[str, int] = {}

        # agent_id -> current status assessment
        self._status: dict[str, AgentStatus] = {}

    def register_agent(self, other_agent_id: str, current_round: int) -> None:
        """Register a known agent (called at startup)."""
        if other_agent_id != self.agent_id:
            self._last_seen[other_agent_id] = current_round
            self._status[other_agent_id] = AgentStatus.ALIVE

    def record_heartbeat(self, from_agent_id: str, current_round: int) -> None:
        """Record that we heard from an agent (either directly or via gossip)."""
        if from_agent_id == self.agent_id:
            return
        self._last_seen[from_agent_id] = current_round
        # Hearing from a suspected agent revives it
        if self._status.get(from_agent_id) == AgentStatus.SUSPECTED:
            self._status[from_agent_id] = AgentStatus.ALIVE

    def check_agents(self, current_round: int) -> dict[str, AgentStatus]:
        """
        Evaluate all known agents' health based on heartbeat recency.

        Called once per round. Returns dict of any status changes.
        """
        changes: dict[str, AgentStatus] = {}

        for agent_id, last_seen in self._last_seen.items():
            old_status = self._status.get(agent_id, AgentStatus.ALIVE)

            # Already confirmed dead — no further transitions
            if old_status == AgentStatus.DEAD:
                continue

            rounds_silent = current_round - last_seen

            if rounds_silent >= DEAD_THRESHOLD:
                new_status = AgentStatus.DEAD
            elif rounds_silent >= SUSPECT_THRESHOLD:
                new_status = AgentStatus.SUSPECTED
            else:
                new_status = AgentStatus.ALIVE

            if new_status != old_status:
                self._status[agent_id] = new_status
                changes[agent_id] = new_status
                self._log_status_change(agent_id, old_status, new_status, rounds_silent, current_round)

            elif rounds_silent > 0 and new_status != AgentStatus.ALIVE:
                # Log ongoing missed heartbeats for transparency
                self._logger.log(
                    EventType.HEARTBEAT_MISS,
                    round_number=current_round,
                    agent_id=self.agent_id,
                    target_agent=agent_id,
                    message=f"{agent_id} silent for {rounds_silent} rounds (status: {new_status.value})",
                    data={"rounds_silent": rounds_silent, "status": new_status.value},
                )

        return changes

    def _log_status_change(
        self,
        target_id: str,
        old_status: AgentStatus,
        new_status: AgentStatus,
        rounds_silent: int,
        current_round: int,
    ) -> None:
        """Log a status transition with full context."""

        if new_status == AgentStatus.SUSPECTED:
            event_type = EventType.AGENT_SUSPECTED
        elif new_status == AgentStatus.DEAD:
            event_type = EventType.AGENT_DEAD
        else:
            event_type = EventType.HEARTBEAT_MISS

        self._logger.log(
            event_type,
            round_number=current_round,
            agent_id=self.agent_id,
            target_agent=target_id,
            message=(
                f"{target_id}: {old_status.value} -> {new_status.value} "
                f"(silent {rounds_silent} rounds, threshold: "
                f"suspect={SUSPECT_THRESHOLD}, dead={DEAD_THRESHOLD})"
            ),
            data={
                "target": target_id,
                "old_status": old_status.value,
                "new_status": new_status.value,
                "rounds_silent": rounds_silent,
            },
        )

    def get_status(self, agent_id: str) -> AgentStatus:
        return self._status.get(agent_id, AgentStatus.ALIVE)

    def get_all_statuses(self) -> dict[str, str]:
        return {aid: s.value for aid, s in self._status.items()}
