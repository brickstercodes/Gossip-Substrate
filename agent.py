"""
AI Agent (Distributed Node) — Report Section 2.1.

Each agent is an independent computational unit that:
  - Holds its own local state (sensor readings it knows about)
  - Participates in gossip rounds (sends and receives state)
  - Tracks other agents' health via failure detection
  - Merges incoming state using the state manager

An agent starts knowing only its own sensor reading. Through repeated
gossip exchanges, it gradually learns what other agents know, until
all alive agents share the same complete picture.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from conflict_resolver import StateEntry
from failure_detector import FailureDetector
from gossip_logger import EventType, GossipLogger
from gossip_protocol import GossipProtocol
from network import GossipMessage, Network
from state_manager import StateManager

if TYPE_CHECKING:
    pass


class Agent:
    """
    A single node in the gossip network.

    Composes the state manager, failure detector, and gossip protocol
    modules. Acts as the orchestration point — receives messages,
    delegates to the right module, and participates in rounds.
    """

    def __init__(
        self,
        agent_id: str,
        initial_sensor: StateEntry,
        network: Network,
        logger: GossipLogger,
        seed: int | None = None,
    ):
        self.agent_id = agent_id
        self.is_alive = True
        self._logger = logger

        # Each agent owns instances of the sub-modules from the report
        self.state_manager = StateManager(agent_id, logger)
        self.failure_detector = FailureDetector(agent_id, logger)
        self.gossip_protocol = GossipProtocol(self, network, seed)

        # Seed the agent with its own sensor reading
        self.state_manager.set_local(initial_sensor)

    def register_peer(self, peer_id: str, current_round: int) -> None:
        """Make this agent aware of another agent in the network."""
        self.failure_detector.register_agent(peer_id, current_round)

    def execute_gossip_round(self, round_number: int, alive_agent_ids: list[str]) -> None:
        """Participate in one gossip round: pick a peer, send state."""
        if not self.is_alive:
            return
        self.gossip_protocol.execute_round(round_number, alive_agent_ids)

    def receive_gossip(self, message: GossipMessage, round_number: int) -> None:
        """
        Process an incoming gossip message from another agent.

        Steps:
          1. Log receipt of the message.
          2. Record that we heard from the sender (heartbeat).
          3. Merge the sender's state into our local state.
        """
        if not self.is_alive:
            return

        self._logger.log(
            EventType.GOSSIP_RECEIVE,
            round_number=round_number,
            agent_id=self.agent_id,
            target_agent=message.sender_id,
            message=f"Received gossip from {message.sender_id} ({len(message.state)} keys)",
            data={"sender": message.sender_id, "keys_received": list(message.state.keys())},
        )

        # Update heartbeat — we know the sender is alive
        self.failure_detector.record_heartbeat(message.sender_id, round_number)

        # Merge the incoming state with our local state
        self.state_manager.merge_incoming(
            incoming_state=message.state,
            sender_id=message.sender_id,
            round_number=round_number,
        )

    def check_failures(self, round_number: int) -> dict[str, str]:
        """Run failure detection and return any status changes."""
        if not self.is_alive:
            return {}
        return {k: v.value for k, v in self.failure_detector.check_agents(round_number).items()}

    def kill(self, round_number: int) -> None:
        """Simulate this agent crashing / going offline."""
        self.is_alive = False
        self._logger.log(
            EventType.AGENT_KILLED,
            round_number=round_number,
            agent_id=self.agent_id,
            message=f"{self.agent_id} has been KILLED (simulating node failure)",
            data={"agent_id": self.agent_id},
        )

    def get_knowledge_count(self, total_sensors: int) -> str:
        """Human-readable progress: how much of total knowledge this agent has."""
        known = len(self.state_manager.state)
        return f"{known}/{total_sensors}"
