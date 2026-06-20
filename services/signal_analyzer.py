"""
Signal Analyzer Helpers
Utility functions for analyzing conversations and patterns
"""

import json
import logging
from typing import List, Dict, Any, Tuple
from datetime import datetime, timedelta

from config.llm import get_llm
from services.signal_types import (
    SignalType, SeverityLevel, UrgencyLevel,
    SIGNAL_DETECTION_CONFIG, SEVERITY_RULES, URGENCY_RULES
)

logger = logging.getLogger(__name__)


class SignalAnalyzer:
    """Analyzes conversations and patterns for signal detection"""
    
    # Keyword mapping for concern types
    KEYWORD_MAPPING = {
        SignalType.EXAM_ANXIETY: [
            "exam", "test", "worried", "anxious", "nervous", "scared",
            "afraid", "panic", "stressed", "overwhelmed", "can't focus",
            "blank mind", "will fail"
        ],
        SignalType.ATTENDANCE_CRISIS: [
            "missed class", "skipped", "didn't attend", "absent", "not going",
            "can't get up", "oversleep", "skip", "bunk", "attendance"
        ],
        SignalType.SCORE_DECLINE: [
            "score dropped", "failed", "flunked", "bad marks", "performed poorly",
            "didn't do well", "low score", "percentage", "got less"
        ],
        SignalType.BURNOUT_RISK: [
            "overwhelmed", "tired", "exhausted", "burned out", "can't cope",
            "too much", "everything at once", "no energy", "drained"
        ],
        SignalType.HEALTH_CONCERN: [
            "sick", "ill", "fever", "headache", "sleep deprivation",
            "not sleeping", "insomnia", "health", "injury", "doctor"
        ],
        SignalType.TIME_MANAGEMENT: [
            "procrastinating", "last minute", "left it till late", "cramming",
            "no time", "deadline", "overcommitted", "can't manage"
        ],
        SignalType.MOTIVATION_DROP: [
            "not interested", "don't care", "why bother", "pointless",
            "doesn't matter", "quit", "drop out", "leave", "give up",
            "no motivation", "demotivated"
        ],
        SignalType.FINANCIAL_STRESS: [
            "money", "afford", "payment", "fees", "broke", "poor",
            "financial", "debt", "can't pay", "expensive"
        ],
        SignalType.EXTERNAL_PRESSURE: [
            "parents", "family", "pressure", "expectations", "forced",
            "don't want to", "conflict", "fight", "argue", "support"
        ],
        SignalType.ACADEMIC_CONFUSION: [
            "don't understand", "confused", "unclear", "lost", "struggling",
            "difficult", "hard", "can't grasp", "not getting it"
        ],
    }
    
    # Intensity multipliers for emotional words
    EMOTIONAL_INTENSITY = {
        "critical": 3.0,
        "harm": 3.0,
        "suicide": 3.0,
        "desperate": 2.5,
        "crisis": 2.5,
        "severe": 2.0,
        "crisis": 2.0,
        "terrible": 2.0,
        "awful": 1.8,
        "horrible": 1.8,
        "panic": 1.8,
        "distressed": 1.5,
        "worried": 1.0,
    }
    
    @staticmethod
    def extract_concerns_from_chat(
        chat_history: List[Dict[str, str]],
        max_concerns: int = 5
    ) -> List[str]:
        """
        Extract concerns from chat using LLM
        
        Edge cases handled:
        - Empty chat history
        - Very long conversations (chunking)
        - LLM failures
        - Invalid message format
        """
        try:
            if not chat_history:
                logger.warning("Empty chat history provided")
                return []
            
            # Chunk long conversations
            chat_text = SignalAnalyzer._format_chat_for_llm(chat_history)
            
            if not chat_text.strip():
                logger.warning("No valid chat content to analyze")
                return []
            
            # Chunk if too long
            max_chars = SIGNAL_DETECTION_CONFIG["conversation_chunk_size"]
            if len(chat_text) > max_chars:
                chat_text = chat_text[-max_chars:]  # Take recent portion
                logger.info(f"Conversation chunked to {len(chat_text)} chars")
            
            llm = get_llm()
            
            prompt = f"""Analyze this student-coach conversation and extract ALL concerning 
            statements or patterns that might warrant a signal.
            
            Focus on: stress, anxiety, health issues, academic problems, time management, 
            motivation drops, financial stress, family pressure, or confusion.
            
            CONVERSATION:
            {chat_text}
            
            Return a JSON array of 1-5 distinct concerns. Be specific with quotes/context:
            [
              "Student mentioned missing 4 classes this week due to oversleeping",
              "Expressed severe anxiety about exam tomorrow: 'I can't focus, I'm panicking'",
              "Said they haven't started studying yet"
            ]
            
            If no concerns, return: []
            """
            
            response = llm.invoke(prompt)
            
            # Parse response safely
            try:
                concerns = json.loads(response.content)
            except json.JSONDecodeError:
                logger.warning("LLM response was not valid JSON, attempting extraction")
                # Fallback: try to extract from text
                concerns = SignalAnalyzer._extract_concerns_fallback(response.content)
            
            if not isinstance(concerns, list):
                concerns = []
            
            # Filter and limit
            valid_concerns = [
                str(c).strip() for c in concerns 
                if isinstance(c, (str, int)) and str(c).strip()
            ][:max_concerns]
            
            return valid_concerns if valid_concerns else []
        
        except Exception as e:
            logger.error(f"❌ Error extracting concerns: {str(e)}")
            return []
    
    @staticmethod
    def _format_chat_for_llm(chat_history: List[Dict[str, str]]) -> str:
        """Format chat history for LLM analysis with error handling"""
        try:
            lines = []
            for i, turn in enumerate(chat_history):
                try:
                    user = turn.get("user", "").strip()
                    assistant = turn.get("assistant", "").strip()
                    
                    if user:
                        lines.append(f"Student: {user}")
                    if assistant:
                        lines.append(f"Coach: {assistant}")
                
                except (TypeError, AttributeError) as e:
                    logger.warning(f"Failed to format turn {i}: {str(e)}")
                    continue
            
            return "\n".join(lines)
        
        except Exception as e:
            logger.error(f"❌ Error formatting chat: {str(e)}")
            return ""
    
    @staticmethod
    def _extract_concerns_fallback(text: str) -> List[str]:
        """Fallback extraction if JSON parsing fails"""
        try:
            # Look for concern-like patterns
            concerns = []
            lines = text.split('\n')
            for line in lines:
                cleaned = line.strip().strip('[],"')
                if len(cleaned) > 20 and cleaned[0].isupper():
                    concerns.append(cleaned)
            return concerns[:5]
        except:
            return []
    
    @staticmethod
    def classify_signal_type(concerns: List[str]) -> Tuple[SignalType, float]:
        """
        Classify concerns into a signal type with confidence score
        
        Edge cases:
        - Empty concerns
        - Multiple concern types
        - Ambiguous language
        """
        try:
            if not concerns:
                return (SignalType.UNCLASSIFIED, 0.0)
            
            concerns_text = " ".join(concerns).lower()
            
            # Score each signal type
            scores = {}
            for signal_type, keywords in SignalAnalyzer.KEYWORD_MAPPING.items():
                score = sum(
                    concerns_text.count(keyword) 
                    for keyword in keywords
                )
                scores[signal_type] = score
            
            # Get top signal type
            if max(scores.values()) == 0:
                return (SignalType.UNCLASSIFIED, 0.3)
            
            best_type = max(scores, key=scores.get)
            confidence = min(scores[best_type] / 10, 1.0)  # Normalize
            
            return (best_type, confidence)
        
        except Exception as e:
            logger.warning(f"Error classifying signal type: {str(e)}")
            return (SignalType.UNCLASSIFIED, 0.0)
    
    @staticmethod
    def assess_severity(
        concerns: List[str],
        signal_type: SignalType,
        pattern_history: Dict[str, Any]
    ) -> SeverityLevel:
        """
        Assess severity level with rules and pattern analysis
        
        Edge cases:
        - Safety-related concerns (always CRITICAL)
        - Recurring patterns
        - Conflicting signals
        """
        try:
            concerns_text = " ".join(concerns).lower()
            
            # CRITICAL checks (overrides everything)
            critical_keywords = ["suicide", "harm", "death", "kill myself", "ending it"]
            if any(kw in concerns_text for kw in critical_keywords):
                logger.warning("🔴 CRITICAL: Safety concern detected")
                return SeverityLevel.CRITICAL
            
            # Check pattern frequency
            recurring_count = pattern_history.get("recurring_concerns", [])
            is_recurring = len(recurring_count) >= SIGNAL_DETECTION_CONFIG["min_pattern_frequency"]
            
            # Apply rules
            high_keywords = ["severe", "crisis", "desperate", "can't cope", "failing", "probation"]
            has_high_indicators = any(kw in concerns_text for kw in high_keywords)
            
            if is_recurring and has_high_indicators:
                return SeverityLevel.CRITICAL
            elif is_recurring or has_high_indicators:
                return SeverityLevel.HIGH
            elif any(kw in concerns_text for kw in ["worried", "stressed", "confused"]):
                return SeverityLevel.MEDIUM
            else:
                return SeverityLevel.LOW
        
        except Exception as e:
            logger.warning(f"Error assessing severity: {str(e)}")
            return SeverityLevel.MEDIUM
    
    @staticmethod
    def assess_urgency(
        severity: SeverityLevel,
        concerns: List[str],
        signal_type: SignalType
    ) -> UrgencyLevel:
        """
        Assess urgency level based on severity and timeliness
        
        Edge cases:
        - Exam timing not clearly specified
        - Multiple urgent factors
        - Low severity but time-sensitive
        """
        try:
            concerns_text = " ".join(concerns).lower()
            
            # CRITICAL/HIGH always urgent
            if severity in (SeverityLevel.CRITICAL, SeverityLevel.HIGH):
                # Check if also time-sensitive
                urgent_time_keywords = ["today", "tomorrow", "now", "immediately", "urgent", "asap"]
                if any(kw in concerns_text for kw in urgent_time_keywords):
                    return UrgencyLevel.TODAY
                return UrgencyLevel.TOMORROW
            
            # Check for immediate time sensitivity
            if any(word in concerns_text for word in ["exam tomorrow", "exam today", "deadline today", "deadline tomorrow"]):
                return UrgencyLevel.TODAY
            
            # MEDIUM and LOW are informational or tomorrow
            return UrgencyLevel.INFORMATIONAL
        
        except Exception as e:
            logger.warning(f"Error assessing urgency: {str(e)}")
            return UrgencyLevel.INFORMATIONAL
    
    @staticmethod
    def extract_evidence(concerns: List[str], max_length: int = 500) -> str:
        """
        Create evidence string from concerns with character limit
        
        Edge cases:
        - Very long concern text
        - Invalid characters
        - Empty concerns
        """
        try:
            if not concerns:
                return "No direct evidence available"
            
            evidence_parts = [f"• {concern[:100]}" for concern in concerns[:3]]
            evidence = "\n".join(evidence_parts)
            
            if len(evidence) > max_length:
                evidence = evidence[:max_length - 3] + "..."
            
            return evidence
        
        except Exception as e:
            logger.warning(f"Error extracting evidence: {str(e)}")
            return "Error extracting evidence"