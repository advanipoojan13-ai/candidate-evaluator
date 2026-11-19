"""Channel selection and component scoring for SafeGold customer support."""

from .roles import SAFEGOLD_COMPONENTS, SAFEGOLD_MEDIUM_COLUMN, SAFEGOLD_MEDIUM_SCORE


CHANNEL_COMPONENTS = "Support Channel Components"
COMPONENT_MAXIMA = {"evidence": 4, "recency": 3, "duration": 3}
MEDIUM_RULES = {
    "Calls + Chat": (1.0, ("Calls", "Chat")),
    "Calls": (0.8, ("Calls",)),
    "Chat": (0.6, ("Chat",)),
    "Email": (0.4, ("Email",)),
    "Social Media": (0.2, ("Social Media",)),
}
CHANNELS = tuple(label for label, (_, channels) in MEDIUM_RULES.items() if len(channels) == 1)


def channel_components_schema() -> dict:
    channel = {
        "type": "object",
        "additionalProperties": False,
        "required": list(COMPONENT_MAXIMA),
        "properties": {
            name: {"type": "integer", "minimum": int(name == "evidence"), "maximum": maximum}
            for name, maximum in COMPONENT_MAXIMA.items()
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(CHANNELS),
        "properties": {name: {"anyOf": [channel, {"type": "null"}]} for name in CHANNELS},
    }


def apply_support_medium(row: dict) -> float:
    """Validate model components, fill C6, and return its multiplier."""
    for category, rule in SAFEGOLD_COMPONENTS.items():
        if category == SAFEGOLD_MEDIUM_SCORE:
            continue
        for column, maximum in rule.column_maxima:
            value = row.get(column)
            if type(value) is not int or not 0 <= value <= maximum:
                raise ValueError(f"{column} must be a JSON integer from 0 to {maximum}.")

    channels = row.get(CHANNEL_COMPONENTS)
    if not isinstance(channels, dict) or channels.keys() != set(CHANNELS):
        raise ValueError("Provide a component entry for each SafeGold support channel.")
    for name, entry in channels.items():
        if entry is None:
            continue
        if not isinstance(entry, dict) or entry.keys() != COMPONENT_MAXIMA.keys():
            raise ValueError(f"{name} must contain all three support channel components or be null.")
        for component, maximum in COMPONENT_MAXIMA.items():
            value = entry[component]
            minimum = int(component == "evidence")
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValueError(f"{name} {component} must be a JSON integer from {minimum} to {maximum}.")

    label, multiplier, chosen = next(
        (
            (label, weight, required)
            for label, (weight, required) in MEDIUM_RULES.items()
            if all(channels[channel] is not None for channel in required)
        ),
        ("", 0.0, ()),
    )
    row[SAFEGOLD_MEDIUM_COLUMN] = label
    for column, component in zip(SAFEGOLD_COMPONENTS[SAFEGOLD_MEDIUM_SCORE].columns, COMPONENT_MAXIMA):
        row[column] = min((channels[channel][component] for channel in chosen), default=0)
    return multiplier
