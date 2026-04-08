"""
Caller script — pass one or more U.S. state names to energy_search.py.

Usage:
    python states.py "Texas"
    python states.py "New York"
"""

import sys
from energy_search import main, VALID_STATES


def run(states: list[str]):
    """
    Iterate over a list of state names and run a search for each valid one.

    Args:
        states: List of state name strings from CLI.
    """
    for state in states:
        state = state.strip().title()

        if state not in VALID_STATES:
            print(f"⚠️  Skipping '{state}' — not a recognized U.S. state.")
            continue

        print(f"\n{'='*50}")
        print(f"  🗺️  State: {state}")
        print(f"{'='*50}")
        main(state)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_states.py <State> [<State2>...]")
        print('Example: python run_states.py Texas "New York" California')
        sys.exit(1)

    states = sys.argv[1:]
    run(states)