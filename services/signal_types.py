"""
Signal Types & Enums
Complete type definitions for Phase 3 signal detection system
"""

import uuid
from typing import TypedDict, List, Dict, Any, Optional
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field, validator


class SeverityLevel(str, Enum):
    """How serious the issue is - determines intervention level"""
    CRITICAL = "critical"      # Immediate risk to student safety/academics
    HIGH = "high"              # Significant impact, needs attention in <24hrs
    MEDIUM = "medium"          # Important but can wait a few days
    LOW = "low"                # Informational tracking only


class UrgencyLevel(str, Enum):
    """When does coach need to act - determines scheduling"""
    TODAY = "today"                      # See student before end of day
    TOMORROW = "tomorrow"                # Within next 24 hours
    INFORMATIONAL = "informational"      # Just for trending/history


class SignalType(str, Enum):
    """Categories of concerns that can be detected"""
    EXAM_ANXIETY = "exam_anxiety"
    ATTENDANCE_CRISIS = "attendance_crisis"
    SCORE_DECLINE = "score_decline"
    BURNOUT_RISK = "burnout_risk"
    HEALTH_CONCERN = "health_concern"
    TIME_MANAGEMENT = "time_management"
    MOTIVATION_DROP = "motivation_drop"
    FINANCIAL_STRESS = "financial_stress"
    EXTERNAL_PRESSURE = "external_pressure"
    ACADEMIC_CONFUSION = "academic_confusion"
    UNCLASSIFIED = "unclassified"  # Fallback for unknown concerns


class Signal(BaseModel):
    """A detected concern that needs coach attention"""
    signal_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    student_id: str
    session_id: str
    signal_type: SignalType
    description: str
    severity: SeverityLevel
    urgency: UrgencyLevel
    evidence: str  # Quotes from conversation supporting signal
    created_at: datetime = Field(default_factory=datetime.now)
    reviewed: bool = False
    coach_notes: str = ""
    is_duplicate: bool = False  # Flag if similar to recent signal
    previous_signal_id: Optional[str] = None  # Link to related signal
    
    @validator("description")
    def validate_description(cls, v):
        """Ensure description is not empty"""
        if not v or len(v.strip()) == 0:
            raise ValueError("Description cannot be empty")
        return v.strip()
    
    @validator("evidence")
    def validate_evidence(cls, v):
        """Ensure evidence has substance"""
        if not v or len(v.strip()) < 10:
            raise ValueError("Evidence must be at least 10 characters")
        return v.strip()


class SignalDetectionState(TypedDict):
    """State that flows through the LangGraph"""
    # ---- INPUT ----
    student_id: str
    session_id: str
    chat_history: List[Dict[str, str]]
    student_name: str
    student_memory: Dict[str, Any]  # From Mem0
    
    # ---- PROCESSING OUTPUTS ----
    extracted_concerns: List[str]      # What's concerning
    pattern_history: Dict[str, Any]    # Past patterns from Mem0
    signal_type: Optional[SignalType]  # Classified concern
    severity: Optional[SeverityLevel]  # Severity assessment
    urgency: Optional[UrgencyLevel]    # Urgency assessment
    
    # ---- FINAL OUTPUT ----
    signal: Optional[Signal]           # The created signal
    should_notify: bool                # Does coach need alert?
    notification_sent: bool            # Was alert sent?
    
    # ---- ERROR HANDLING ----
    error: Optional[str]               # Any errors during processing
    error_node: Optional[str]          # Which node failed
    retry_count: int                   # How many retries attempted


class SignalFilters(BaseModel):
    """Filters for querying signals"""
    student_id: Optional[str] = None
    severity: Optional[List[SeverityLevel]] = None
    urgency: Optional[List[UrgencyLevel]] = None
    signal_type: Optional[List[SignalType]] = None
    reviewed: Optional[bool] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    limit: int = 50
    offset: int = 0


class SignalAnalysis(BaseModel):
    """Analysis summary for a student"""
    student_id: str
    total_signals: int
    signals_this_week: int
    critical_count: int
    high_count: int
    recent_pattern: Optional[str]  # e.g., "exam_anxiety_recurring"
    recommendations: List[str]
    last_signal_at: Optional[datetime]


# Constants for signal detection
SIGNAL_DETECTION_CONFIG = {
    "max_concerns_per_session": 5,  # Limit concerns extracted
    "min_pattern_frequency": 2,  # How many times to be "recurring"
    "exam_timeframe_hours": 48,  # Hours ahead = exam urgency
    "attendance_threshold": 60,  # Percentage below = crisis
    "score_decline_threshold": 15,  # Percentage drop = concern
    "conversation_chunk_size": 2000,  # Chars per LLM analysis chunk
    "max_retries": 2,  # Retry failed operations
    "deduplication_hours": 6,  # Don't flag same concern within 6hrs
}

# Severity decision rules (readable reference)
SEVERITY_RULES = {
    "CRITICAL": [
        "student mentions harm/suicide",
        "academic probation imminent",
        "score below 30%",
        "attendance below 40%",
        "third mental health crisis this month",
    ],
    "HIGH": [
        "recurring issue (3+ times in history)",
        "strong anxiety with exam in <48hrs",
        "score drop >20%",
        "attendance drop >25%",
        "health issue affecting performance",
    ],
    "MEDIUM": [
        "new concern mentioned",
        "moderate stress indicators",
        "attendance issue but not crisis",
        "confusion with one subject",
        "procrastination noted",
    ],
    "LOW": [
        "minor issue mentioned once",
        "general stress (no indicators)",
        "low academic priority",
        "informational only",
    ]
}

# Urgency decision rules
URGENCY_RULES = {
    "TODAY": [
        "severity=critical",
        "exam or major deadline in <24hrs",
        "third stress episode this week",
        "health crisis mentioned",
    ],
    "TOMORROW": [
        "severity=high",
        "exam in 2-3 days",
        "attendance dropping rapidly",
        "confusion with material",
    ],
    "INFORMATIONAL": [
        "severity=medium or low",
        "new pattern, single mention",
        "general tracking",
    ]
}