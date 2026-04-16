"""
Gossip Communication Layer — Report Section 2.2.

This is the core gossip algorithm from Section 4 of the report:

  1. At fixed intervals (each round), each agent randomly picks a peer.
  2. The agent sends its full state to that peer.
  3. The peer compares received state with its own and merges newer data.
  4. Over time, all agents converge to the same global state.

We use a "push" gossip model: the initiating agent sends its state TO
the selected peer. The alternative is "push-pull" where both agents
exchange state simultaneously — that converges faster but is harder
to follow in the logs. Push-only is clearer for the demo.

Peer selection is uniformly random among alive agents (excluding self).
This randomness is what gives gossip protocols their scalability —
no agent needs to know the full network topology.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from network import GossipMessage

if TYPE_CHECKING:
    from agent import Agent
    from network import Network


class GossipProtocol:
    """
    Implements the peer selection and message preparation steps
    of the gossip algorithm.
    """

    def __init__(self, agent: "Agent", network: "Network", seed: int | None = None):
        self._agent = agent
        self._network = network
        # Seeded RNG so the simulation is reproducible for demos
        self._rng = random.Random(seed)

    def execute_round(self, round_number: int, alive_agent_ids: list[str]) -> None:
        """
        Run one gossip round for this agent.

        Steps:
          1. Select a random peer from the alive agents (excluding self).
          2. Package current state into a GossipMessage.
          3. Send via the network layer.
          4. If delivery fails, the agent's failure detector will be
             updated by the caller (main loop).
        """
        peer_id = self._select_peer(alive_agent_ids)
        if peer_id is None:
            return

        message = self._prepare_message(round_number)
        delivered = self._network.send_gossip(
            sender=self._agent,
            target_id=peer_id,
            message=message,
            round_number=round_number,
        )

        if delivered:
            # Successful delivery implies the target is alive (like a TCP ACK).
            # Without this, push-only gossip creates false suspicions because
            # an agent only hears FROM peers who randomly select it as a target.
            self._agent.failure_detector.record_heartbeat(peer_id, round_number)

    def _select_peer(self, alive_agent_ids: list[str]) -> str | None:
        """
        Uniformly random peer selection, excluding self.

        Returns None if no peers available (all dead or alone in network).
        """
        candidates = [aid for aid in alive_agent_ids if aid != self._agent.agent_id]
        if not candidates:
            return None
        return self._rng.choice(candidates)

    def _prepare_message(self, round_number: int) -> GossipMessage:
        """Package this agent's current state into a gossip message."""
        return GossipMessage(
            sender_id=self._agent.agent_id,
            state=self._agent.state_manager.state,
            agent_statuses=self._agent.failure_detector.get_all_statuses(),
            round_number=round_number,
        )
