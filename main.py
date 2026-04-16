"""
Gossip-Enhanced Communication Substrate — Simulation Runner.

This is the entry point that wires everything together and runs the demo.
It creates 5 agents, each with one unique sensor reading, runs the gossip
protocol for a configurable number of rounds, kills Agent_D mid-way to
demonstrate fault tolerance, and outputs a final convergence report.

Output:
  - Color-coded terminal logs (real-time transparency)
  - simulation_log.json (structured events for the HTML dashboard)
  - Auto-opens dashboard.html in the browser after completion

Usage:
  python main.py                     # default settings
  python main.py --rounds 20         # run for 20 rounds
  python main.py --seed 42           # reproducible randomness
  python main.py --kill-round 6      # kill Agent_D at round 6
  python main.py --no-dashboard      # skip auto-opening browser
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import webbrowser
from pathlib import Path

from agent import Agent
from conflict_resolver import StateEntry
from gossip_logger import EventType, GossipLogger
from network import Network


# --- Simulation Configuration ---

SENSOR_DATA = [
    {"key": "temperature", "value": 22.5, "unit": "C", "agent": "Agent_A"},
    {"key": "humidity", "value": 65.0, "unit": "%", "agent": "Agent_B"},
    {"key": "wind_speed", "value": 12.3, "unit": "km/h", "agent": "Agent_C"},
    {"key": "pressure", "value": 1013.25, "unit": "hPa", "agent": "Agent_D"},
    {"key": "air_quality", "value": 42.0, "unit": "AQI", "agent": "Agent_E"},
]

AGENT_KILL_TARGET = "Agent_D"


def create_agents(
    network: Network,
    logger: GossipLogger,
    base_seed: int,
) -> list[Agent]:
    """
    Initialize 5 agents, each with one unique sensor reading.

    Each agent starts knowing only its own reading. Through gossip,
    they will eventually all know all 5 readings.
    """
    agents: list[Agent] = []
    start_time = time.time()

    for i, sensor in enumerate(SENSOR_DATA):
        entry = StateEntry(
            key=sensor["key"],
            value=sensor["value"],
            unit=sensor["unit"],
            version=1,
            timestamp=start_time,
            source_agent=sensor["agent"],
        )
        agent = Agent(
            agent_id=sensor["agent"],
            initial_sensor=entry,
            network=network,
            logger=logger,
            seed=base_seed + i,
        )
        network.register_agent(agent)
        agents.append(agent)

    # Make all agents aware of each other
    for agent in agents:
        for other in agents:
            if other.agent_id != agent.agent_id:
                agent.register_peer(other.agent_id, current_round=0)

    return agents


def check_convergence(agents: list[Agent], total_sensors: int) -> bool:
    """
    Check if all alive agents have the same complete state.

    Convergence = every alive agent knows all sensor readings from
    all agents that were ever in the network.
    """
    alive_agents = [a for a in agents if a.is_alive]
    for agent in alive_agents:
        if len(agent.state_manager.state) < total_sensors:
            return False
    return True


def print_round_summary(
    agents: list[Agent],
    round_number: int,
    total_sensors: int,
    logger: GossipLogger,
) -> None:
    """Print a compact summary of each agent's knowledge after a round."""
    summary_lines = []
    agent_states = {}

    for agent in agents:
        if agent.is_alive:
            count = agent.get_knowledge_count(total_sensors)
            keys = sorted(agent.state_manager.state.keys())
            summary_lines.append(f"  {agent.agent_id}: {count} known -> {keys}")
            agent_states[agent.agent_id] = {
                "alive": True,
                "knowledge_count": len(agent.state_manager.state),
                "known_keys": keys,
                "state": agent.state_manager.get_state_snapshot(),
            }
        else:
            summary_lines.append(f"  {agent.agent_id}: DEAD")
            agent_states[agent.agent_id] = {"alive": False}

    logger.log(
        EventType.ROUND_SUMMARY,
        round_number=round_number,
        message="Round summary:\n" + "\n".join(summary_lines),
        data={
            "agents": agent_states,
            "total_sensors": total_sensors,
        },
    )


def run_simulation(
    num_rounds: int = 15,
    kill_round: int = 5,
    seed: int = 42,
    open_dashboard: bool = True,
) -> None:
    """
    Main simulation loop implementing the gossip algorithm from Section 4.

    Pseudocode from the report:
      Initialize local state S for each agent
      Repeat periodically:
          Select random peer agent j
          Send local state S to agent j
      Upon receiving state Sj:
          Merge Sj with local state S
          Update local knowledge
    """
    script_dir = Path(__file__).parent
    log_path = script_dir / "simulation_log.json"
    logger = GossipLogger(str(log_path))

    total_sensors = len(SENSOR_DATA)

    # --- Initialization ---
    logger.log(
        EventType.SIMULATION_START,
        round_number=-1,
        message=(
            f"Starting Gossip-Enhanced Communication Substrate\n"
            f"  Agents: {len(SENSOR_DATA)} | Rounds: {num_rounds} | "
            f"Kill {AGENT_KILL_TARGET} at round {kill_round} | Seed: {seed}"
        ),
        data={
            "num_agents": len(SENSOR_DATA),
            "num_rounds": num_rounds,
            "kill_round": kill_round,
            "kill_target": AGENT_KILL_TARGET,
            "seed": seed,
            "sensors": SENSOR_DATA,
        },
    )

    network = Network(logger)
    agents = create_agents(network, logger, base_seed=seed)
    agent_map = {a.agent_id: a for a in agents}

    converged = False
    convergence_round = -1

    # --- Main Gossip Loop ---
    for round_num in range(1, num_rounds + 1):
        logger.log(
            EventType.ROUND_START,
            round_number=round_num,
            message=f"{'='*60} ROUND {round_num} {'='*60}",
        )

        # Kill the target agent at the designated round
        if round_num == kill_round and AGENT_KILL_TARGET in agent_map:
            agent_map[AGENT_KILL_TARGET].kill(round_num)

        # Each alive agent executes one gossip round
        alive_ids = network.get_alive_agent_ids()
        for agent in agents:
            if agent.is_alive:
                agent.execute_gossip_round(round_num, alive_ids)

        # Each alive agent checks for failures
        for agent in agents:
            if agent.is_alive:
                agent.check_failures(round_num)

        # Print round summary
        print_round_summary(agents, round_num, total_sensors, logger)

        # Check for convergence among alive agents
        if not converged and check_convergence(agents, total_sensors):
            converged = True
            convergence_round = round_num
            logger.log(
                EventType.CONVERGENCE,
                round_number=round_num,
                message=(
                    f"CONVERGENCE ACHIEVED at round {round_num}! "
                    f"All alive agents have complete state ({total_sensors}/{total_sensors} sensors)"
                ),
                data={"convergence_round": round_num},
            )

    # --- Final Report ---
    logger.log(
        EventType.SIMULATION_END,
        round_number=num_rounds,
        message=(
            f"Simulation complete after {num_rounds} rounds. "
            f"{'Converged at round ' + str(convergence_round) if converged else 'Did NOT converge'}"
        ),
        data={
            "converged": converged,
            "convergence_round": convergence_round,
            "final_states": {
                a.agent_id: {
                    "alive": a.is_alive,
                    "state": a.state_manager.get_state_snapshot() if a.is_alive else {},
                }
                for a in agents
            },
        },
    )

    # Save JSON log for the dashboard
    saved_path = logger.save_json()
    print(f"\n{'='*60}")
    print(f"  Log saved to: {saved_path}")
    print(f"  Total events: {len(logger.events)}")
    print(f"{'='*60}\n")

    # Auto-open dashboard
    if open_dashboard:
        dashboard_path = script_dir / "dashboard.html"
        if dashboard_path.exists():
            webbrowser.open(f"file://{dashboard_path.resolve()}")
            print(f"  Dashboard opened in browser: {dashboard_path}")
        else:
            print(f"  Dashboard not found at: {dashboard_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Gossip Protocol Simulation")
    parser.add_argument("--rounds", type=int, default=15, help="Number of gossip rounds")
    parser.add_argument("--kill-round", type=int, default=5, help="Round to kill Agent_D")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument("--no-dashboard", action="store_true", help="Skip opening dashboard")

    args = parser.parse_args()

    run_simulation(
        num_rounds=args.rounds,
        kill_round=args.kill_round,
        seed=args.seed,
        open_dashboard=not args.no_dashboard,
    )


if __name__ == "__main__":
    main()
