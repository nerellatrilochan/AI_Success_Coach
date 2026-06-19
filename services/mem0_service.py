import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from mem0 import MemoryClient

load_dotenv()

class Mem0SessionService:
    """
    Service to handle session persistence using Mem0 Platform
    
    Key features:
    - Saves only key facts (infer=True extracts automatically)
    - Does NOT store raw chat history
    - Proper error handling for Mem0 API
    """
    
    def __init__(self):
        """Initialize Mem0 client with API key from .env"""
        api_key = os.getenv("MEM0_API_KEY")
        if not api_key:
            raise ValueError("MEM0_API_KEY not found in .env file")
        
        self.client = MemoryClient(api_key=api_key)
        print("✅ Mem0 client initialized successfully")
    
    def save_session(
        self,
        student_id: str,
        student_name: str,
        session_id: str,
        chat_history: List[Dict[str, str]],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Save a completed chat session to Mem0.
        
        Uses infer=True: Mem0 automatically extracts key facts from conversation.
        This means ONLY important facts are stored, not the entire chat.
        
        Args:
            student_id: Unique student identifier
            student_name: Name of the student
            session_id: Unique session identifier
            chat_history: List of dicts with "user" and "assistant" keys
            metadata: Optional metadata to attach
        
        Returns:
            memory_id if successful, None if error
        """
        try:
            if not chat_history:
                print("⚠️  No chat history to save")
                return None
            
            # Convert to Mem0 message format
            messages = []
            for turn in chat_history:
                user_msg = turn.get("user", "").strip()
                assistant_msg = turn.get("assistant", "").strip()
                
                if user_msg:
                    messages.append({"role": "user", "content": user_msg})
                if assistant_msg:
                    messages.append({"role": "assistant", "content": assistant_msg})
            
            if not messages:
                print("⚠️  No valid messages to save")
                return None
            
            # Build metadata
            session_metadata = {
                "session_id": session_id,
                "student_name": student_name,
                "message_count": len(chat_history),
                "session_ended_at": datetime.now().isoformat(),
                "session_category": "coaching_session"
            }
            
            if metadata:
                session_metadata.update(metadata)
            
            print(f"\n{'='*70}")
            print(f"💾 SAVING SESSION TO MEM0 (Key Facts Only)")
            print(f"   Student: {student_name} (ID: {student_id})")
            print(f"   Session ID: {session_id}")
            print(f"   Chat Messages: {len(chat_history)}")
            print(f"   Mem0 will extract key facts automatically...")
            print(f"{'='*70}\n")
            
            # Save with infer=True (default)
            result = self.client.add(
                messages=messages,
                user_id=student_id,
                metadata=session_metadata,
            )
            
            memory_ids = result.get("memory_ids") if isinstance(result, dict) else None
            
            print(f"✅ Session saved! Mem0 extracted and stored key facts.")
            if memory_ids:
                print(f"   Memory ID: {memory_ids[0] if memory_ids else 'Generated'}\n")
            
            return memory_ids[0] if memory_ids else "saved"
        
        except Exception as e:
            print(f"❌ Error saving session: {str(e)}\n")
            return None
    
    def get_session_history(
        self,
        student_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Retrieve previous sessions for a student.
        
        Args:
            student_id: Student identifier
            limit: Maximum number of sessions to retrieve
        
        Returns:
            List of session memories
        """
        try:
            print(f"\n🔎 Loading previous sessions for student {student_id}...\n")
            
            results = self.client.search(
                query="session coaching chat history",
                filters={
                    "user_id": student_id
                },
                top_k=limit
            )
            
            if not results or not results.get("results"):
                print("No previous sessions found.\n")
                return []
            
            sessions = results.get("results", [])
            print(f"✅ Found {len(sessions)} previous session(s)\n")
            
            return sessions
        
        except Exception as e:
            print(f"⚠️  Error retrieving session history: {str(e)}\n")
            return []
    
    def search_sessions(
        self,
        student_id: str,
        query: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search through a student's session memories.
        
        Args:
            student_id: Student identifier
            query: Natural language search query
            limit: Max results
        
        Returns:
            List of matching memories
        """
        try:
            results = self.client.search(
                query=query,
                filters={
                    "user_id": student_id
                },
                top_k=limit
            )
            
            return results.get("results", []) if results else []
        
        except Exception as e:
            print(f"⚠️  Error searching sessions: {str(e)}")
            return []

    def get_student_memory_context(
        self,
        student_id: str
    ) -> Dict[str, Any]:
        """
        Comprehensive memory retrieval for a student.
        Returns structured memory with factual insights + session summaries.
        
        Returns:
            {
                "session_count": int,
                "factual_memory": str,  # Extracted patterns, triggers, solutions
                "session_summaries": str,  # What was discussed
                "raw_memories": list,  # All memories from Mem0
                "first_time": bool  # True if this is their first session
            }
        """
        try:
            # Retrieve all memories for this student
            results = self.client.search(
                query="student profile stress triggers coping strategies solutions patterns",
                filters={
                    "user_id": student_id
                },
                top_k=50  # Get more results to analyze
            )
            
            memories = results.get("results", []) if results else []
            session_count = len(memories)
            
            if session_count == 0:
                return {
                    "session_count": 0,
                    "factual_memory": "",
                    "session_summaries": "",
                    "raw_memories": [],
                    "first_time": True
                }
            
            print(f"\n{'='*70}")
            print(f"📚 MEMORY CONTEXT FOR STUDENT {student_id}")
            print(f"   Total Sessions: {session_count}")
            print(f"{'='*70}\n")
            
            # Extract factual memory and session summaries
            factual_memory = self._extract_factual_memory(memories)
            session_summaries = self._extract_session_summaries(memories)
            
            return {
                "session_count": session_count,
                "factual_memory": factual_memory,
                "session_summaries": session_summaries,
                "raw_memories": memories,
                "first_time": False
            }
        
        except Exception as e:
            print(f"⚠️  Error retrieving memory context: {str(e)}\n")
            return {
                "session_count": 0,
                "factual_memory": "",
                "session_summaries": "",
                "raw_memories": [],
                "first_time": True
            }

    def _extract_factual_memory(self, memories: List[Dict[str, Any]]) -> str:
        """
        Extract factual memory: stress triggers, patterns, solutions that worked.
        """
        if not memories:
            return ""
        
        factual_items = []
        
        for memory in memories:
            memory_text = memory.get("memory", "")
            
            # Look for stress triggers
            if any(word in memory_text.lower() for word in 
                ["stress", "trigger", "worried", "anxious", "pressure", "overwhelm"]):
                factual_items.append(f"• Stress trigger: {memory_text[:150]}")
            
            # Look for solutions
            if any(word in memory_text.lower() for word in 
                ["helped", "solution", "strategy", "approach", "worked", "effective"]):
                factual_items.append(f"• Effective strategy: {memory_text[:150]}")
            
            # Look for patterns
            if any(word in memory_text.lower() for word in 
                ["pattern", "usually", "often", "always", "habit", "recurring"]):
                factual_items.append(f"• Pattern: {memory_text[:150]}")
        
        return "\n".join(factual_items[:10]) if factual_items else ""

    def _extract_session_summaries(self, memories: List[Dict[str, Any]]) -> str:
        """
        Extract session summaries: what was discussed, what was decided.
        """
        if not memories:
            return ""
        
        summaries = []
        
        for i, memory in enumerate(memories[:5], 1):  # Last 5 sessions
            memory_text = memory.get("memory", "")
            metadata = memory.get("metadata", {})
            timestamp = metadata.get("session_ended_at", "N/A")
            
            summary = f"Session {i} ({timestamp}): {memory_text[:200]}"
            summaries.append(summary)
        
        return "\n".join(summaries) if summaries else ""

    def get_session_count(self, student_id: str) -> int:
        """Get total number of sessions for a student."""
        try:
            results = self.client.search(
                query="session",
                filters={"user_id": student_id},
                top_k=100
            )
            memories = results.get("results", []) if results else []
            return len(memories)
        except Exception as e:
            print(f"⚠️  Error getting session count: {str(e)}")
            return 0


# Singleton instance
_mem0_service = None

def get_mem0_service() -> Mem0SessionService:
    """Get or create Mem0 service instance (lazy initialization)"""
    global _mem0_service
    if _mem0_service is None:
        _mem0_service = Mem0SessionService()
    return _mem0_service