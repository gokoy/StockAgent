from enum import Enum


class ActionLabel(str, Enum):
    CANDIDATE = "candidate"
    OBSERVE = "observe"
    AVOID = "avoid"


class ChartLabel(str, Enum):
    BREAKOUT = "breakout"
    PULLBACK = "pullback"
    RANGE = "range"
    EXTENDED = "extended"
    MIXED = "mixed"


class ConfidenceLabel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
