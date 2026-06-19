"""
Memory Integration Service
Coordinates memory retrieval and prepares personalized context for AI conversations.
"""

from typing import Dict, Any
from services.mem0_service import get_mem0_service


class MemoryIntegrationService:
    """Orchestrates memory operations for personalized conversations"""
    
    def __init__(self):
        self.mem0_service = get_mem0_service()
    
    def prepare_memory_context(
        self,
        student_id: str,
        student_name: str
    ) -> Dict[str, Any]:
        """
        Prepare complete memory context for a conversation.
        
        Returns structured data with all necessary memory info.
        """
        memory_data = self.mem0_service.get_student_memory_context(student_id)
        
        context = {
            "student_id": student_id,
            "student_name": student_name,
            "session_number": memory_data["session_count"] + 1,  # Next session number
            "is_first_session": memory_data["first_time"],
            "factual_memory": memory_data["factual_memory"],
            "session_summaries": memory_data["session_summaries"],
            "has_previous_sessions": memory_data["session_count"] > 0,
            "total_previous_sessions": memory_data["session_count"]
        }
        
        return context
    
    def get_personalization_notes(self, memory_context: Dict[str, Any]) -> str:
        """
        Generate personalization notes for the system prompt.
        """
        if memory_context["is_first_session"]:
            return "This is the student's FIRST session. Be extra welcoming and encouraging."
        
        session_num = memory_context["session_number"]
        
        if session_num <= 3:
            return f"This is session {session_num}. Student is still new. Build rapport and foundational support."
        elif session_num <= 5:
            return f"This is session {session_num}. Student has some history. Reference previous discussions to show continuity."
        else:
            return f"This is session {session_num}. Student is an experienced coach user. Use deep knowledge of their patterns and provide advanced guidance."
    
    def format_memory_briefing(self, memory_context: Dict[str, Any]) -> str:
        """
        Format memory as a briefing for when coach asks for one.
        """
        briefing = f"""
**STUDENT BRIEFING - {memory_context['student_name']}**

Session Number: {memory_context['session_number']}
Previous Sessions: {memory_context['total_previous_sessions']}

**KEY PATTERNS & INSIGHTS:**
{memory_context['factual_memory'] if memory_context['factual_memory'] else 'No previous patterns recorded yet.'}

**SESSION HISTORY:**
{memory_context['session_summaries'] if memory_context['session_summaries'] else 'No previous sessions to reference.'}
        """.strip()
        
        return briefing


# Singleton instance
_memory_integration_service = None


def get_memory_integration_service() -> MemoryIntegrationService:
    """Get or create memory integration service instance"""
    global _memory_integration_service
    if _memory_integration_service is None:
        _memory_integration_service = MemoryIntegrationService()
    return _memory_integration_service