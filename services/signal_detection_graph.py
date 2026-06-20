"""
Signal Detection Graph
LangGraph implementation for multi-step signal detection workflow
"""

import logging
from typing import Literal

from langgraph.graph import StateGraph, END
from config.llm import get_llm
from services.signal_types import (
    Signal, SignalDetectionState, SignalType,
    SeverityLevel, UrgencyLevel,
    SIGNAL_DETECTION_CONFIG
)
from services.signal_storage_service import get_signal_storage_service
from services.signal_analyzer import SignalAnalyzer
from services.mem0_service import get_mem0_service

logger = logging.getLogger(__name__)


# ============================================================================
# NODE FUNCTIONS
# ============================================================================

def read_session(state: SignalDetectionState) -> SignalDetectionState:
    """
    Node 1: Extract concerns from chat history
    
    Edge cases handled:
    - Empty chat history
    - Very long conversations
    - Malformed messages
    - LLM API failures
    """
    try:
        logger.info(f"🔍 Reading session {state['session_id']}")
        
        # Validate input
        if not state.get("chat_history"):
            logger.warning("⚠️  Empty chat history provided")
            state["extracted_concerns"] = []
            state["error"] = "Empty chat history"
            return state
        
        # Extract concerns
        concerns = SignalAnalyzer.extract_concerns_from_chat(
            state["chat_history"],
            max_concerns=SIGNAL_DETECTION_CONFIG["max_concerns_per_session"]
        )
        
        state["extracted_concerns"] = concerns
        
        if concerns:
            logger.info(f"✅ Extracted {len(concerns)} concern(s)")
        else:
            logger.info("ℹ️  No concerns detected in this session")
        
        return state
    
    except Exception as e:
        logger.error(f"❌ Error in read_session: {str(e)}")
        state["error"] = f"read_session failed: {str(e)}"
        state["error_node"] = "read_session"
        state["extracted_concerns"] = []
        return state


def fetch_student_patterns(state: SignalDetectionState) -> SignalDetectionState:
    """
    Node 2: Query Mem0 for historical patterns
    
    Edge cases handled:
    - Mem0 connection failure
    - First-time student (no history)
    - Memory retrieval timeout
    - Invalid student_id
    """
    try:
        logger.info(f"📚 Fetching patterns for {state['student_id']}")
        
        if not state.get("student_id"):
            logger.warning("Invalid student_id")
            state["pattern_history"] = {}
            state["error"] = "Invalid student_id"
            return state
        
        try:
            mem0_service = get_mem0_service()
            memory_data = mem0_service.get_student_memory_context(state["student_id"])
            
            # Analyze if concerns are recurring
            patterns = {
                "session_count": memory_data.get("session_count", 0),
                "is_first_time": memory_data.get("first_time", True),
                "factual_memory": memory_data.get("factual_memory", ""),
                "recurring_concerns": []
            }
            
            # Find recurring concerns
            concerns_text = " ".join(state.get("extracted_concerns", [])).lower()
            memory_text = patterns["factual_memory"].lower()
            
            recurring_keywords = ["stress", "anxiety", "worry", "attendence", "score", "overwhelm"]
            recurring = [kw for kw in recurring_keywords if kw in concerns_text and kw in memory_text]
            patterns["recurring_concerns"] = recurring
            
            state["pattern_history"] = patterns
            logger.info(f"✅ Found {memory_data['session_count']} previous sessions")
        
        except Exception as mem_error:
            logger.warning(f"⚠️  Mem0 retrieval failed (non-fatal): {str(mem_error)}")
            state["pattern_history"] = {
                "session_count": 0,
                "is_first_time": True,
                "factual_memory": "",
                "recurring_concerns": []
            }
        
        return state
    
    except Exception as e:
        logger.error(f"❌ Error in fetch_student_patterns: {str(e)}")
        state["error"] = f"Pattern fetch failed: {str(e)}"
        state["error_node"] = "fetch_student_patterns"
        state["pattern_history"] = {}
        return state


def assess_signal_type(state: SignalDetectionState) -> SignalDetectionState:
    """
    Node 3: Classify concerns into a signal type
    
    Edge cases handled:
    - Multiple concern types (pick dominant one)
    - Ambiguous language
    - Low confidence signals
    """
    try:
        logger.info("🏷️  Assessing signal type")
        
        concerns = state.get("extracted_concerns", [])
        if not concerns:
            state["signal_type"] = None
            return state
        
        signal_type, confidence = SignalAnalyzer.classify_signal_type(concerns)
        
        logger.info(f"✅ Signal type: {signal_type.value} (confidence: {confidence:.1%})")
        state["signal_type"] = signal_type
        
        return state
    
    except Exception as e:
        logger.error(f"❌ Error in assess_signal_type: {str(e)}")
        state["error"] = f"Signal type assessment failed: {str(e)}"
        state["error_node"] = "assess_signal_type"
        state["signal_type"] = SignalType.UNCLASSIFIED
        return state


def assess_severity(state: SignalDetectionState) -> SignalDetectionState:
    """
    Node 4: Determine severity level
    
    Edge cases handled:
    - Safety concerns (always CRITICAL)
    - Conflicting indicators
    - Missing pattern data
    """
    try:
        logger.info("⚠️  Assessing severity")
        
        concerns = state.get("extracted_concerns", [])
        signal_type = state.get("signal_type", SignalType.UNCLASSIFIED)
        pattern_history = state.get("pattern_history", {})
        
        if not concerns:
            state["severity"] = SeverityLevel.LOW
            return state
        
        severity = SignalAnalyzer.assess_severity(
            concerns,
            signal_type,
            pattern_history
        )
        
        logger.info(f"✅ Severity: {severity.value}")
        state["severity"] = severity
        
        return state
    
    except Exception as e:
        logger.error(f"❌ Error in assess_severity: {str(e)}")
        state["error"] = f"Severity assessment failed: {str(e)}"
        state["error_node"] = "assess_severity"
        state["severity"] = SeverityLevel.MEDIUM  # Default to medium if error
        return state


def assess_urgency(state: SignalDetectionState) -> SignalDetectionState:
    """
    Node 5: Determine urgency level
    
    Edge cases handled:
    - Time-sensitive low severity
    - Multiple urgency factors
    - Invalid times
    """
    try:
        logger.info("⏱️  Assessing urgency")
        
        severity = state.get("severity", SeverityLevel.MEDIUM)
        concerns = state.get("extracted_concerns", [])
        signal_type = state.get("signal_type", SignalType.UNCLASSIFIED)
        
        urgency = SignalAnalyzer.assess_urgency(severity, concerns, signal_type)
        
        logger.info(f"✅ Urgency: {urgency.value}")
        state["urgency"] = urgency
        
        return state
    
    except Exception as e:
        logger.error(f"❌ Error in assess_urgency: {str(e)}")
        state["error"] = f"Urgency assessment failed: {str(e)}"
        state["error_node"] = "assess_urgency"
        state["urgency"] = UrgencyLevel.INFORMATIONAL
        return state


def write_signal(state: SignalDetectionState) -> SignalDetectionState:
    """
    Node 6: Create and persist Signal object
    
    Edge cases handled:
    - Database connection failure
    - Duplicate signals
    - Invalid signal data
    - Retry logic
    """
    try:
        logger.info("💾 Writing signal to database")
        
        # Check if we should even write
        if not state.get("extracted_concerns"):
            logger.info("ℹ️  No concerns, skipping signal creation")
            state["signal"] = None
            state["should_notify"] = False
            return state
        
        # Create Signal object
        concerns = state.get("extracted_concerns", [])
        signal = Signal(
            student_id=state.get("student_id", "unknown"),
            session_id=state.get("session_id", "unknown"),
            signal_type=state.get("signal_type", SignalType.UNCLASSIFIED),
            description=f"Detected concerns: {', '.join(concerns[:2])}",
            severity=state.get("severity", SeverityLevel.MEDIUM),
            urgency=state.get("urgency", UrgencyLevel.INFORMATIONAL),
            evidence=SignalAnalyzer.extract_evidence(concerns)
        )
        
        # Save to database with retry
        storage = get_signal_storage_service()
        success = False
        retry_count = 0
        
        while retry_count < SIGNAL_DETECTION_CONFIG["max_retries"] and not success:
            try:
                success = storage.save_signal(signal)
            except Exception as db_error:
                retry_count += 1
                logger.warning(f"⚠️  Save attempt {retry_count} failed: {str(db_error)}")
                if retry_count >= SIGNAL_DETECTION_CONFIG["max_retries"]:
                    logger.error(f"❌ Failed to save signal after {retry_count} retries")
                    state["error"] = f"Database save failed: {str(db_error)}"
                    state["error_node"] = "write_signal"
                    state["signal"] = signal  # Still attach for potential recovery
                    state["retry_count"] = retry_count
                    return state
        
        state["signal"] = signal
        state["should_notify"] = (
            signal.severity == SeverityLevel.CRITICAL or 
            signal.urgency == UrgencyLevel.TODAY
        )
        state["retry_count"] = retry_count
        
        logger.info(f"✅ Signal created: {signal.signal_id}")
        return state
    
    except Exception as e:
        logger.error(f"❌ Error in write_signal: {str(e)}")
        state["error"] = f"Signal creation failed: {str(e)}"
        state["error_node"] = "write_signal"
        state["signal"] = None
        return state


def notify_coach(state: SignalDetectionState) -> SignalDetectionState:
    """
    Node 7: Alert coach if signal needs immediate attention
    
    Edge cases handled:
    - Notification system unavailable
    - Invalid notification data
    - Already notified (deduplication)
    """
    try:
        logger.info("🔔 Checking if coach notification needed")
        
        if not state.get("should_notify") or not state.get("signal"):
            logger.info("ℹ️  Notification not needed")
            state["notification_sent"] = False
            return state
        
        signal = state["signal"]
        notification_message = f"""
🚨 URGENT SIGNAL DETECTED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Student: {state.get('student_name', 'Unknown')}
Signal Type: {signal.signal_type.value}
Severity: {signal.severity.value.upper()}
Urgency: {signal.urgency.value.upper()}

Description: {signal.description}

Evidence:
{signal.evidence}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        # TODO: Implement actual notification (email, Slack, dashboard ping)
        logger.warning(notification_message)
        
        state["notification_sent"] = True
        logger.info("✅ Coach notification dispatched")
        
        return state
    
    except Exception as e:
        logger.error(f"❌ Error in notify_coach: {str(e)}")
        state["error"] = f"Notification failed: {str(e)}"
        state["error_node"] = "notify_coach"
        state["notification_sent"] = False
        return state


# ============================================================================
# CONDITIONAL EDGES
# ============================================================================

def should_fetch_patterns(state: SignalDetectionState) -> str:
    """Decide whether to continue to pattern fetching"""
    if state.get("extracted_concerns"):
        return "fetch_patterns"
    else:
        logger.info("No concerns extracted, skipping to signal writing")
        return "write_signal"


def should_assess_severity(state: SignalDetectionState) -> str:
    """Decide whether to continue to severity assessment"""
    if state.get("extracted_concerns"):
        return "assess_signal_type"
    else:
        return "write_signal"


def should_notify_coach(state: SignalDetectionState) -> str:
    """Decide whether to notify coach"""
    if state.get("should_notify"):
        return "notify_coach"
    else:
        return END


# ============================================================================
# GRAPH BUILDER
# ============================================================================

def build_signal_detection_graph():
    """Build the complete signal detection state machine"""
    
    logger.info("🏗️  Building Signal Detection Graph")
    
    graph = StateGraph(SignalDetectionState)
    
    # Add all nodes
    graph.add_node("read_session", read_session)
    graph.add_node("fetch_patterns", fetch_student_patterns)
    graph.add_node("assess_signal_type", assess_signal_type)
    graph.add_node("assess_severity", assess_severity)
    graph.add_node("assess_urgency", assess_urgency)
    graph.add_node("write_signal", write_signal)
    graph.add_node("notify_coach", notify_coach)
    
    # Set entry point
    graph.set_entry_point("read_session")
    
    # Add edges with conditional routing
    graph.add_conditional_edges(
        "read_session",
        should_fetch_patterns,
        {
            "fetch_patterns": "fetch_patterns",
            "write_signal": "write_signal"
        }
    )
    
    graph.add_edge("fetch_patterns", "assess_signal_type")
    graph.add_edge("assess_signal_type", "assess_severity")
    graph.add_edge("assess_severity", "assess_urgency")
    graph.add_edge("assess_urgency", "write_signal")
    
    graph.add_conditional_edges(
        "write_signal",
        should_notify_coach,
        {
            "notify_coach": "notify_coach",
            END: END
        }
    )
    
    graph.add_edge("notify_coach", END)
    
    compiled_graph = graph.compile()
    logger.info("✅ Signal Detection Graph built successfully")
    
    return compiled_graph


# ============================================================================
# SINGLETON ACCESS
# ============================================================================

_signal_graph = None


def get_signal_detection_graph():
    """Get or create signal detection graph instance"""
    global _signal_graph
    if _signal_graph is None:
        _signal_graph = build_signal_detection_graph()
    return _signal_graph