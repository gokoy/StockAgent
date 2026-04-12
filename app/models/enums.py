from enum import Enum


class ActionLabel(str, Enum):
    CANDIDATE = "candidate"
    OBSERVE = "observe"
    AVOID = "avoid"


class HoldingStatus(str, Enum):
    KEEP = "keep"
    POSITIVE_WATCH = "positive_watch"
    CAUTION = "caution"
    REDUCE = "reduce"
    REVIEW = "review"


class CandidateStatus(str, Enum):
    BUY = "buy"
    WATCH = "watch"
    NONE = "none"


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
