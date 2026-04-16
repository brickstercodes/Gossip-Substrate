"""
Structured logging for full gossip protocol transparency.

This module exists because the demo's primary goal is showing a professor
what happens under the hood. Every gossip exchange, state merge, conflict
resolution, and failure detection is logged twice:
  1. Color-coded terminal output (human-readable during the run)
  2. Structured JSON events (consumed by the HTML dashboard after the run)

The JSON log is the bridge between the Python simulation and the dashboard.
"""

import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class EventType(Enum):
    """Categories of observable events in the gossip system."""

    # Gossip lifecycle
    ROUND_START = "ROUND_START"
    GOSSIP_SEND = "GOSSIP_SEND"
    GOSSIP_RECEIVE = "GOSSIP_RECEIVE"
    GOSSIP_FAILED = "GOSSIP_FAILED"

    # State changes
    STATE_MERGE = "STATE_MERGE"
    STATE_NO_CHANGE = "STATE_NO_CHANGE"
    CONFLICT_RESOLVED = "CONFLICT_RESOLVED"

    # Failure detection
    HEARTBEAT_MISS = "HEARTBEAT_MISS"
    AGENT_SUSPECTED = "AGENT_SUSPECTED"
    AGENT_DEAD = "AGENT_DEAD"
    AGENT_KILLED = "AGENT_KILLED"

    # Simulation milestones
    ROUND_SUMMARY = "ROUND_SUMMARY"
    CONVERGENCE = "CONVERGENCE"
    SIMULATION_START = "SIMULATION_START"
    SIMULATION_END = "SIMULATION_END"


# Terminal color codes for readable output
_COLORS = {
    EventType.ROUND_START: "\033[1;36m",       # Bold cyan
    EventType.GOSSIP_SEND: "\033[0;34m",        # Blue
    EventType.GOSSIP_RECEIVE: "\033[0;32m",     # Green
    EventType.GOSSIP_FAILED: "\033[0;31m",      # Red
    EventType.STATE_MERGE: "\033[0;33m",        # Yellow
    EventType.STATE_NO_CHANGE: "\033[0;90m",    # Gray
    EventType.CONFLICT_RESOLVED: "\033[0;35m",  # Magenta
    EventType.HEARTBEAT_MISS: "\033[0;91m",     # Light red
    EventType.AGENT_SUSPECTED: "\033[1;33m",    # Bold yellow
    EventType.AGENT_DEAD: "\033[1;31m",         # Bold red
    EventType.AGENT_KILLED: "\033[1;31m",       # Bold red
    EventType.ROUND_SUMMARY: "\033[0;97m",      # White
    EventType.CONVERGENCE: "\033[1;32m",        # Bold green
    EventType.SIMULATION_START: "\033[1;97m",   # Bold white
    EventType.SIMULATION_END: "\033[1;97m",     # Bold white
}
_RESET = "\033[0m"

# Icons for terminal output to make scanning easier
_ICONS = {
    EventType.ROUND_START: "=",
    EventType.GOSSIP_SEND: "->",
    EventType.GOSSIP_RECEIVE: "<-",
    EventType.GOSSIP_FAILED: "XX",
    EventType.STATE_MERGE: "++",
    EventType.STATE_NO_CHANGE: "..",
    EventType.CONFLICT_RESOLVED: "<>",
    EventType.HEARTBEAT_MISS: "?!",
    EventType.AGENT_SUSPECTED: "??",
    EventType.AGENT_DEAD: "XX",
    EventType.AGENT_KILLED: "!!",
    EventType.ROUND_SUMMARY: "--",
    EventType.CONVERGENCE: "OK",
    EventType.SIMULATION_START: ">>",
    EventType.SIMULATION_END: "<<",
}


@dataclass
class LogEvent:
    """A single observable event in the gossip system."""

    event_type: str
    round_number: int
    timestamp: float
    agent_id: str = ""
    target_agent: str = ""
    message: str = ""
    data: dict = field(default_factory=dict)


class GossipLogger:
    """
    Dual-output logger: terminal (colored) + JSON file (for dashboard).

    Usage:
        logger = GossipLogger("simulation_log.json")
        logger.log(EventType.GOSSIP_SEND, round=1, agent="Agent_A",
                    target="Agent_C", message="Sending state",
                    data={"keys_sent": ["temperature"]})
    """

    def __init__(self, json_output_path: str):
        self._events: list[LogEvent] = []
        self._json_path = json_output_path
        self._start_time = time.time()

    def log(
        self,
        event_type: EventType,
        round_number: int,
        agent_id: str = "",
        target_agent: str = "",
        message: str = "",
        data: dict | None = None,
    ) -> None:
        """Record an event to both terminal and the JSON event list."""

        event = LogEvent(
            event_type=event_type.value,
            round_number=round_number,
            timestamp=time.time() - self._start_time,
            agent_id=agent_id,
            target_agent=target_agent,
            message=message,
            data=data or {},
        )
        self._events.append(event)
        self._print_terminal(event_type, event)

    def _print_terminal(self, event_type: EventType, event: LogEvent) -> None:
        """Print a colored, human-readable line to the terminal."""

        color = _COLORS.get(event_type, "")
        icon = _ICONS.get(event_type, "  ")
        round_label = f"[Round {event.round_number:>2}]" if event.round_number >= 0 else "[      ]"

        agent_label = f" {event.agent_id}" if event.agent_id else ""
        target_label = f" -> {event.target_agent}" if event.target_agent else ""

        print(f"{color}{round_label} {icon}{agent_label}{target_label} | {event.message}{_RESET}")

    def save_json(self) -> str:
        """Write all events to the JSON file for the dashboard to consume."""

        output = [asdict(e) for e in self._events]
        with open(self._json_path, "w") as f:
            json.dump(output, f, indent=2)
        return self._json_path

    @property
    def events(self) -> list[LogEvent]:
        return self._events
