from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from config.llm import get_llm
from services.google_sheets_service import get_student_profile
from services.rag_service import initialize_rag_service
from prompts.system_prompts import (
    get_student_data_system_prompt,
    get_knowledge_base_system_prompt,
    get_general_question_system_prompt,
    get_off_topic_response,
    validate_input,
    get_memory_aware_system_prompt,
    get_briefing_system_prompt
)
import json

# Initialize RAG service globally (once)
rag_service = None
rag_initialized = False

def get_rag_service(force_rebuild: bool = False):
    """Get or initialize RAG service (lazy initialization)"""
    global rag_service, rag_initialized
    if rag_service is None:
        print("\n🚀 Initializing RAG Service on first use...")
        rag_service = initialize_rag_service(
            knowledge_file_path="Knowledge.md",
            force_rebuild=force_rebuild or not rag_initialized
        )
        rag_initialized = True
    return rag_service


# ============================================================================
# TOOL DECORATED FUNCTIONS
# ============================================================================

@tool
def get_attendance_data(student_id: str) -> str:
    """
    Fetch the student's detailed attendance record including weekly breakdown, 
    classes attended/scheduled, attendance percentages, and overall statistics.
    """
    profile = get_student_profile(student_id)
    attendance = profile.get("attendance", [])
    
    if not attendance:
        return "No attendance data available for you."
    
    output = ["📊 YOUR ATTENDANCE RECORD:\n"]
    for record in attendance:
        week = record.get('week_of', 'N/A')
        attended = record.get('classes_attended', 0)
        scheduled = record.get('classes_scheduled', 0)
        pct = record.get('attendance_pct', 'N/A')
        output.append(f"  • Week of {week}: {attended}/{scheduled} classes ({pct}%)")
    
    try:
        total_attended = sum(int(r.get('classes_attended', 0)) for r in attendance if r.get('classes_attended', ''))
        total_scheduled = sum(int(r.get('classes_scheduled', 0)) for r in attendance if r.get('classes_scheduled', ''))
        overall_pct = (total_attended / total_scheduled * 100) if total_scheduled > 0 else 0
        output.append(f"\n📈 OVERALL: {total_attended}/{total_scheduled} classes ({overall_pct:.1f}%)")
    except:
        pass
    
    return "\n".join(output)


@tool
def get_exam_scores(student_id: str) -> str:
    """
    Fetch the student's exam scores, marks, percentages, dates, and analysis.
    """
    profile = get_student_profile(student_id)
    exam_scores = profile.get("exam_scores", [])
    
    if not exam_scores:
        return "No exam scores available yet."
    
    output = ["📝 YOUR EXAM SCORES:\n"]
    percentages = []
    
    for score in exam_scores:
        subject = score.get('subject', 'N/A')
        obtained = score.get('score', 0)
        max_score = score.get('max_score', 100)
        pct = score.get('percentage', 0)
        date = score.get('date', 'N/A')
        percentages.append(pct)
        
        output.append(f"  • {subject}: {obtained}/{max_score} ({pct}%) - Exam date: {date}")
    
    if percentages:
        avg_pct = sum(percentages) / len(percentages)
        max_pct = max(percentages)
        min_pct = min(percentages)
        
        output.append(f"\n📊 STATISTICS:")
        output.append(f"    Average Score: {avg_pct:.1f}%")
        output.append(f"    Highest Score: {max_pct}%")
        output.append(f"    Lowest Score: {min_pct}%")
        
        strongest = exam_scores[percentages.index(max_pct)]['subject']
        weakest = exam_scores[percentages.index(min_pct)]['subject']
        output.append(f"    Strongest Subject: {strongest} ({max_pct}%)")
        output.append(f"    Weakest Subject: {weakest} ({min_pct}%)")
    
    return "\n".join(output)


@tool
def get_exam_schedule(student_id: str) -> str:
    """
    Fetch the student's upcoming exam schedule.
    """
    profile = get_student_profile(student_id)
    exam_schedule = profile.get("exam_schedule", [])
    
    if not exam_schedule:
        return "No upcoming exams scheduled at this time."
    
    output = [f"📅 YOUR UPCOMING EXAMS ({len(exam_schedule)} total):\n"]
    for exam in exam_schedule:
        subject = exam.get('subject', 'N/A')
        date = exam.get('exam_date', 'N/A')
        exam_type = exam.get('exam_type', 'N/A')
        output.append(f"  • {subject}: {date} ({exam_type})")
    
    return "\n".join(output)


@tool
def get_student_roster(student_id: str) -> str:
    """
    Fetch the student's basic profile information.
    """
    profile = get_student_profile(student_id)
    roster = profile.get("roster", {})
    
    if not roster:
        return "No student profile information available."
    
    output = [
        "👤 YOUR STUDENT PROFILE:",
        f"  • Name: {roster.get('name', 'N/A')}",
        f"  • Student ID: {roster.get('student_id', 'N/A')}",
        f"  • Program: {roster.get('program', 'N/A')}",
        f"  • Cohort: {roster.get('cohort', 'N/A')}",
        f"  • Manager Email: {roster.get('manager_email', 'N/A')}",
    ]
    
    return "\n".join(output)


@tool
def search_knowledge_base(query: str) -> str:
    """
    Search the CCBP Academy knowledge base.
    """
    try:
        print(f"\n{'='*70}")
        print(f"🔎 KNOWLEDGE BASE SEARCH REQUEST")
        print(f"Query: {query}")
        print(f"{'='*70}\n")
        
        rag_service = get_rag_service()
        llm = get_llm()
        
        answer = rag_service.get_answer_from_knowledge_base(llm, query, k=7)
        
        print(f"\n{'='*70}")
        print(f"✅ SEARCH COMPLETED")
        print(f"{'='*70}\n")
        
        return answer
    except Exception as e:
        print(f"❌ Error in search_knowledge_base: {str(e)}")
        import traceback
        traceback.print_exc()
        return f"I encountered an error while searching the knowledge base: {str(e)}"


# ============================================================================
# ENHANCED QUESTION CLASSIFIER
# ============================================================================

def classify_question(question: str, student_id: str) -> dict:
    """
    Intelligent question classifier with guardrails
    """
    question_lower = question.lower().strip()
    
    # Profile-related keywords (HIGHEST PRIORITY)
    profile_keywords = [
        "who am i", "who i am", "tell me about myself", "my profile",
        "who is my", "what is my name", "my student id", "my program",
        "my cohort", "my manager", "about me", "tell me who i am"
    ]
    
    # Attendance-related keywords
    attendance_keywords = [
        "attendance", "attend", "classes", "missed", "absent", "skipped",
        "week", "how many classes", "absent too much"
    ]
    
    # Exam scores keywords
    scores_keywords = [
        "score", "marks", "exam score", "percentage", "subject", "strong", "weak",
        "average", "highest", "lowest", "performance", "how did i score", "what are my marks"
    ]
    
    # Exam schedule keywords
    schedule_keywords = [
        "exam", "schedule", "when", "upcoming", "test date", "next exam",
        "do i have", "any exams", "exam timing"
    ]
    
    # Knowledge base keywords
    kb_keywords = [
        # Portal and access
        "learning.ccbp.in", "learning portal", "how to access", "login", "otp",
        "portal access", "register", "access the portal",
        
        # Home page
        "home page", "dashboard", "upcoming events", "schedule", "learning schedule",
        "performance metrics", "consistency", "monthly activity", "leaderboard",
        
        # My Journey
        "my journey", "growth cycle", "gc1", "gc2", "gc3", "gc4", "gc5",
        "progress", "cycle", "topics", "assignments", "projects", "unlock",
        
        # Milestones
        "milestone", "internship", "placement", "job opportunity", "career",
        
        # Course Exams
        "course exam", "exam guide", "exam schedule", "exam timing", "exam date",
        "retake", "camera", "grading", "grades", "pass exam",
        
        # Certificates
        "certificate", "course certificate", "eligibility", "completion",
        "100% course", "certificate access",
        
        # Search
        "search", "find content", "content discovery", "search option",
        
        # Bookmarks
        "bookmark", "save question", "saved questions",
        
        # Bonus courses
        "bonus course", "extra learning", "advanced topics",
        
        # LastMinute Pro
        "lastminute", "placement", "off-campus", "mock interview",
        
        # General KB
        "what is", "tell me about", "explain", "how does", "feature", "overview"
    ]
    
    # OFF-TOPIC detection (BLOCK THESE)
    off_topic_keywords = [
        "python", "java", "javascript", "code", "program", "software",
        "math", "science", "english", "history", "chemistry", "physics",
        "solve", "calculate", "write code", "homework help", "do my assignment",
        "hack", "exploit", "password", "secret"
    ]
    
    # Check for off-topic questions
    for keyword in off_topic_keywords:
        if keyword in question_lower:
            # If it's genuinely about learning (kb), allow it
            if not any(kb in question_lower for kb in ["learning", "course", "platform", "portal"]):
                return {
                    "type": "off_topic",
                    "tools_to_use": [],
                    "parameters": {},
                    "confidence": 0.95
                }
    
    # Check for profile keywords (HIGHEST PRIORITY)
    for keyword in profile_keywords:
        if keyword in question_lower:
            return {
                "type": "student_data",
                "tools_to_use": ["profile"],
                "parameters": {"student_id": student_id},
                "confidence": 0.95
            }
    
    # Check for attendance keywords
    for keyword in attendance_keywords:
        if keyword in question_lower:
            return {
                "type": "student_data",
                "tools_to_use": ["attendance"],
                "parameters": {"student_id": student_id},
                "confidence": 0.95
            }
    
    # Check for exam scores keywords
    for keyword in scores_keywords:
        if keyword in question_lower:
            return {
                "type": "student_data",
                "tools_to_use": ["scores"],
                "parameters": {"student_id": student_id},
                "confidence": 0.95
            }
    
    # Check for exam schedule keywords
    for keyword in schedule_keywords:
        if keyword in question_lower:
            return {
                "type": "student_data",
                "tools_to_use": ["schedule"],
                "parameters": {"student_id": student_id},
                "confidence": 0.95
            }
    
    # Check for knowledge base keywords
    for keyword in kb_keywords:
        if keyword in question_lower:
            return {
                "type": "knowledge_base",
                "tools_to_use": ["search_knowledge_base"],
                "parameters": {"query": question},
                "confidence": 0.95
            }
    
    # Default: treat as general or knowledge base
    return {
        "type": "general",
        "tools_to_use": [],
        "parameters": {},
        "confidence": 0.5
    }


# ============================================================================
# HELPER FUNCTION - Execute Student Data Tools (FIX FOR WARNING)
# ============================================================================

def _execute_student_data_tools(tools_to_use: list, parameters: dict) -> str:
    """
    Execute student data tools and return formatted results.
    This function was missing - now defined!
    
    Args:
        tools_to_use: List of tool names to execute ("profile", "attendance", "scores", "schedule")
        parameters: Dict with student_id
    
    Returns:
        Formatted string with tool results
    """
    tools_map = {
        "attendance": get_attendance_data,
        "scores": get_exam_scores,
        "schedule": get_exam_schedule,
        "profile": get_student_roster,
    }
    
    student_id = parameters.get("student_id", "")
    tool_results = {}
    
    for tool_name in tools_to_use:
        if tool_name in tools_map:
            try:
                result = tools_map[tool_name].invoke({"student_id": student_id})
                tool_results[tool_name] = result
            except Exception as e:
                tool_results[tool_name] = f"Error fetching {tool_name}: {str(e)}"
    
    # Format tool results
    if not tool_results:
        return "No tool results available."
    
    formatted_results = "\n\n".join([
        f"📌 {name.upper()}:\n{result}"
        for name, result in tool_results.items()
    ])
    
    return formatted_results


# ============================================================================
# MAIN AGENT BUILDER - WITH MEMORY
# ============================================================================

def build_conversation_agent(student_id: str, student_name: str):
    """
    Build conversation agent with memory context injected.
    
    INCLUDES:
    - Student's memory context (previous sessions, patterns, triggers)
    - Personalized system prompt based on session number
    - Session-aware responses
    - Briefing capability for student history
    """
    from services.memory_integration import get_memory_integration_service
    
    # Get memory context for this student
    memory_service = get_memory_integration_service()
    memory_context = memory_service.prepare_memory_context(student_id, student_name)
    
    print(f"\n{'='*70}")
    print(f"🧠 AGENT INITIALIZATION WITH MEMORY")
    print(f"   Student: {student_name} ({student_id})")
    print(f"   Session: {memory_context['session_number']}")
    print(f"   Previous Sessions: {memory_context['total_previous_sessions']}")
    print(f"   First Time: {memory_context['is_first_session']}")
    print(f"{'='*70}\n")
    
    # Build the memory-aware system prompt
    system_prompt = get_memory_aware_system_prompt(
        student_name=student_name,
        memory_context=memory_context
    )
    
    llm = get_llm()
    
    def agent_function(user_input: str, chat_history: list) -> str:
        """Execute agent with memory-aware context"""
        
        # Check for briefing request
        briefing_keywords = ["tell me about", "what do you know", "briefing", "summary"]
        is_briefing_request = any(
            keyword in user_input.lower() for keyword in briefing_keywords
        )
        
        if is_briefing_request:
            # Use special briefing prompt
            briefing = memory_service.format_memory_briefing(memory_context)
            briefing_system_prompt = get_briefing_system_prompt(briefing)
            messages = [SystemMessage(content=briefing_system_prompt)]
        else:
            # Use regular memory-aware system prompt
            messages = [SystemMessage(content=system_prompt)]
        
        # Add chat history
        for turn in chat_history:
            messages.append(HumanMessage(content=turn["user"]))
            messages.append(AIMessage(content=turn["assistant"]))
        
        # Add current input
        messages.append(HumanMessage(content=user_input))
        
        # Classify the question to route to right tools
        classification = classify_question(user_input, student_id)
        
        # Determine which system prompt to use based on question type
        if classification["type"] == "student_data":
            tools_result = _execute_student_data_tools(
                classification["tools_to_use"],
                classification["parameters"]
            )
            messages[-1] = HumanMessage(
                content=f"{user_input}\n\n[TOOL RESULTS]\n{tools_result}"
            )
        
        elif classification["type"] == "knowledge_base":
            query = classification["parameters"].get("query", user_input)
            kb_result = search_knowledge_base(query)
            messages[-1] = HumanMessage(
                content=f"{user_input}\n\n[KNOWLEDGE BASE RESULT]\n{kb_result}"
            )
        
        elif classification["type"] == "off_topic":
            messages[-1] = HumanMessage(
                content=f"{user_input}\n\n[RESPONSE REQUIRED]\nPlease provide an off-topic response."
            )
            return get_off_topic_response()
        
        # Get LLM response
        try:
            response = llm.invoke(messages)
            return response.content
        except Exception as e:
            return f"I encountered an error: {str(e)}"
    
    return agent_function