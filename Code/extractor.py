import re


def extract_fields(text: str) -> dict:
    """
    Heuristic extraction. This is intentionally conservative.
    """

    place_match = re.search(
        r"(United States|U\.S\.|California|Texas|New York|Florida|Canada|EU)",
        text,
        re.IGNORECASE
    )

    incentive_match = re.search(
        r"(tax credit|rebate|grant|subsidy|deduction|incentive)",
        text,
        re.IGNORECASE
    )

    return {
        "name": incentive_match.group(0).title() if incentive_match else "Clean Energy Incentive",
        "place": place_match.group(0) if place_match else "Unknown",
        "incentive": text
    }
