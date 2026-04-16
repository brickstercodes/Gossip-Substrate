"""
Communication Interface Layer — Report Section 2.6.

This module simulates the network between agents. In a real distributed
system, this would be TCP/UDP sockets, gRPC, or HTTP. Here, agents
communicate through direct method calls with simulated behavior:

  - Message delivery is synchronous (simplifies the round-based demo)
  - Dead agents return None (simulates network timeout)
  - All messages pass through this layer so we get a single point of
    observability for the logger

The abstraction matters because it decouples agent logic from transport.
An agent calls network.send() without knowing whether the peer is local,
remote, or dead. The network layer handles that.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gossip_logger import EventType, GossipLogger

if TYPE_CHECKING:
    from agent import Agent
    from conflict_resolver import StateEntry


class GossipMessage:
    """
    The payload exchanged between agents during a gossip round.

    Contains the sender's full state snapshot and their view of agent
    health statuses (so failure detection info also propagates via gossip).
    """

    def __init__(
        self,
        sender_id: str,
        state: dict[str, "StateEntry"],
        agent_statuses: dict[str, str],
        round_number: int,
    ):
        self.sender_id = sender_id
        self.state = state
        self.agent_statuses = agent_statuses
        self.round_number = round_number


class Network:
    """
    Simulated network for inter-agent communication.

    Holds references to all agents and routes messages between them.
    A dead agent's messages silently fail (returning None), which the
    sender's failure detector will pick up on.
    """

    def __init__(self, logger: GossipLogger):
        self._agents: dict[str, "Agent"] = {}
        self._logger = logger

    def register_agent(self, agent: "Agent") -> None:
        self._agents[agent.agent_id] = agent

    def send_gossip(
        self,
        sender: "Agent",
        target_id: str,
        message: GossipMessage,
        round_number: int,
    ) -> bool:
        """
        Deliver a gossip message from sender to target.

        Returns True if delivered successfully, False if target is unreachable
        (dead or unknown). The caller uses this to update failure detection.
        """
        target = self._agents.get(target_id)

        if target is None or not target.is_alive:
            self._logger.log(
                EventType.GOSSIP_FAILED,
                round_number=round_number,
                agent_id=sender.agent_id,
                target_agent=target_id,
                message=f"Failed to reach {target_id} (node is down)",
                data={"reason": "target_dead" if target and not target.is_alive else "target_unknown"},
            )
            return False

        # Log the send
        state_keys = list(message.state.keys())
        self._logger.log(
            EventType.GOSSIP_SEND,
            round_number=round_number,
            agent_id=sender.agent_id,
            target_agent=target_id,
            message=f"Sending state ({len(state_keys)} keys: {state_keys})",
            data={
                "keys_sent": state_keys,
                "state_snapshot": {k: v.to_dict() for k, v in message.state.items()},
            },
        )

        # Deliver to target — the target processes it synchronously
        target.receive_gossip(message, round_number)
        return True

    def get_alive_agent_ids(self) -> list[str]:
        return [aid for aid, agent in self._agents.items() if agent.is_alive]
