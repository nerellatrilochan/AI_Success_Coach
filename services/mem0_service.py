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
            
            # Build metadata - NO 'type' field in filters!
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
            # This makes Mem0 extract structured facts, not store raw chat
            result = self.client.add(
                messages=messages,
                user_id=student_id,
                metadata=session_metadata,
                # infer=True is DEFAULT - Mem0 extracts key facts automatically
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
        
        IMPORTANT: Only uses 'user_id' filter - NO 'type' filter!
        The 'type' filter is NOT supported by Mem0 API.
        
        Args:
            student_id: Student identifier
            limit: Maximum number of sessions to retrieve
        
        Returns:
            List of session memories
        """
        try:
            print(f"\n🔎 Loading previous sessions for student {student_id}...\n")
            
            # FIXED: ONLY use 'user_id' filter - removed 'type' filter!
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


# Singleton instance
_mem0_service = None

def get_mem0_service() -> Mem0SessionService:
    """Get or create Mem0 service instance (lazy initialization)"""
    global _mem0_service
    if _mem0_service is None:
        _mem0_service = Mem0SessionService()
    return _mem0_service