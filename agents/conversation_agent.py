from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from config.llm import get_llm
from services.google_sheets_service import get_student_profile
from services.rag_service import initialize_rag_service
import json

SYSTEM_PROMPT = """
You are Success Coach AI, an intelligent assistant designed to support college and university students with their academic success.

Your mission is to help students excel academically, professionally, and personally.

CORE RESPONSIBILITIES:
1. Answer questions about student-specific data (attendance, exam scores, exams, profile)
2. Answer questions about CCBP Academy features, learning portal, courses, and platform guidance
3. Provide academic guidance and study tips
4. Help with career planning and professional development
5. Offer time management and productivity advice
6. Support skill development and learning
"""

# Initialize RAG service globally (once) - with force_rebuild on first run
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
# TOOL DECORATED FUNCTIONS WITH PROPER IMPLEMENTATION
# ============================================================================

@tool
def get_attendance_data(student_id: str) -> str:
    """
    Fetch the student's detailed attendance record including weekly breakdown, 
    classes attended/scheduled, attendance percentages, and overall statistics.
    
    Args:
        student_id: The unique student identifier
        
    Returns:
        Formatted attendance report with statistics
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
    
    # Calculate overall statistics
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
    Fetch the student's exam scores, marks, percentages, dates, and analysis 
    of strongest and weakest subjects with statistics.
    
    Args:
        student_id: The unique student identifier
        
    Returns:
        Formatted exam scores report with analysis
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
    
    # Calculate statistics
    if percentages:
        avg_pct = sum(percentages) / len(percentages)
        max_pct = max(percentages)
        min_pct = min(percentages)
        
        output.append(f"\n📊 STATISTICS:")
        output.append(f"    Average Score: {avg_pct:.1f}%")
        output.append(f"    Highest Score: {max_pct}%")
        output.append(f"    Lowest Score: {min_pct}%")
        
        # Find strongest and weakest subjects
        strongest = exam_scores[percentages.index(max_pct)]['subject']
        weakest = exam_scores[percentages.index(min_pct)]['subject']
        output.append(f"    Strongest Subject: {strongest} ({max_pct}%)")
        output.append(f"    Weakest Subject: {weakest} ({min_pct}%)")
    
    return "\n".join(output)


@tool
def get_exam_schedule(student_id: str) -> str:
    """
    Fetch the student's upcoming exam schedule including subjects, dates, and exam types.
    
    Args:
        student_id: The unique student identifier
        
    Returns:
        Formatted upcoming exams list
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
    Fetch the student's basic profile information including name, student ID, 
    program, cohort, and manager email.
    
    Args:
        student_id: The unique student identifier
        
    Returns:
        Formatted student profile information
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
    Search the CCBP Academy knowledge base to answer questions about:
    - Learning Portal features and access (learning.ccbp.in, login, OTP)
    - Home Page (dashboard, events, performance metrics)
    - My Journey (growth cycles, milestones, progress tracking)
    - Course Exams (schedules, how they work, retakes, grading)
    - Course Certificates (eligibility, issuance, access)
    - Search functionality and content discovery
    - Bookmarks (saving and accessing questions)
    - Bonus Courses (additional learning opportunities)
    - LastMinute Pro (placement preparation)
    
    Use this tool for any questions about CCBP Academy features and platform functionality.
    
    Args:
        query: The student's question about CCBP Academy
        
    Returns:
        Comprehensive answer based on knowledge base content
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
# IMPROVED QUESTION CLASSIFIER
# ============================================================================

def classify_question(question: str, student_id: str) -> dict:
    """
    Intelligent question classifier that routes to appropriate tool
    
    Returns:
        {
            "type": "student_data" | "knowledge_base" | "general",
            "tools_to_use": list of tool names,
            "parameters": dict of parameters,
            "confidence": float between 0 and 1
        }
    """
    question_lower = question.lower()
    
    # Enhanced keywords for student data queries
    student_keywords = {
        "attendance": [
            "attendance", "attend", "classes", "missed", "absent", "skipped",
            "week", "how many classes", "absent too much"
        ],
        "scores": [
            "score", "marks", "exam score", "percentage", "subject", "strong", "weak",
            "average", "highest", "lowest", "performance", "how did i score", "what are my marks"
        ],
        "schedule": [
            "exam", "schedule", "when", "upcoming", "test date", "next exam",
            "do i have", "any exams", "exam timing"
        ],
        "profile": [
            "profile", "name", "program", "cohort", "manager", "student id", 
            "tell me about myself", "who is my manager"
        ],
    }
    
    # Enhanced keywords for knowledge base queries
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
        "course exam", "exam", "exam schedule", "exam timing", "exam date",
        "retake", "camera", "grading", "grades", "pass exam", "exam tips",
        
        # Certificates
        "certificate", "course certificate", "eligibility", "completion",
        "100% course", "certificate access", "email certificate",
        
        # Search
        "search", "find content", "content discovery", "search option",
        
        # Bookmarks
        "bookmark", "save question", "saved questions", "bookmarked",
        
        # Bonus courses
        "bonus course", "extra learning", "advanced topics", "foundation",
        "programming course", "interview readiness",
        
        # LastMinute Pro
        "lastminute", "placement", "off-campus", "mock interview", "mock test",
        "interview prep", "resume", "project", "company preparation",
        
        # General questions
        "what is", "how do i", "tell me about", "explain", "how does",
        "guide", "steps", "instructions", "how to", "feature", "overview"
    ]
    
    # Check for student data keywords
    for category, keywords in student_keywords.items():
        for keyword in keywords:
            if keyword in question_lower:
                return {
                    "type": "student_data",
                    "tools_to_use": [category],
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
    
    # Default to knowledge base for ambiguous questions (better to use KB than miss it)
    return {
        "type": "knowledge_base",
        "tools_to_use": ["search_knowledge_base"],
        "parameters": {"query": question},
        "confidence": 0.5
    }


# ============================================================================
# MAIN AGENT BUILDER
# ============================================================================

def build_conversation_agent(*, student_id: str = "", student_name: str = ""):
    """
    Build a conversation agent that intelligently routes questions to appropriate tools.
    
    Args:
        student_id: The student's unique identifier
        student_name: The student's name
        
    Returns:
        A function that processes user messages and returns responses
    """
    
    llm = get_llm()
    
    # Define all available tools
    tools_map = {
        "attendance": get_attendance_data,
        "scores": get_exam_scores,
        "schedule": get_exam_schedule,
        "profile": get_student_roster,
        "search_knowledge_base": search_knowledge_base,
    }
    
    def run(user_message: str, history: list[dict]) -> str:
        """
        Process user message and generate response.
        
        Args:
            user_message: The student's question
            history: Conversation history
            
        Returns:
            The assistant's response
        """
        
        try:
            print(f"\n{'='*70}")
            print(f"📨 NEW MESSAGE FROM STUDENT")
            print(f"Message: {user_message}")
            print(f"{'='*70}\n")
            
            # Step 1: Classify the question
            classification = classify_question(user_message, student_id)
            question_type = classification["type"]
            tools_to_use = classification["tools_to_use"]
            parameters = classification["parameters"]
            confidence = classification["confidence"]
            
            print(f"📊 Classification: {question_type.upper()} (confidence: {confidence:.1%})")
            print(f"   Tools: {tools_to_use}\n")
            
            # Step 2: Handle based on question type
            if question_type == "general":
                return _answer_general_question(llm, user_message, history, student_name)
            
            elif question_type == "student_data":
                return _answer_student_question(llm, user_message, history, tools_to_use, student_id, student_name)
            
            elif question_type == "knowledge_base":
                return _answer_knowledge_base_question(user_message)
            
        except Exception as e:
            print(f"❌ Error in agent: {str(e)}")
            import traceback
            traceback.print_exc()
            return f"I apologize, but I encountered an error: {str(e)}"
    
    return run


# ============================================================================
# HELPER FUNCTIONS FOR DIFFERENT QUESTION TYPES
# ============================================================================

def _answer_general_question(llm, user_message: str, history: list[dict], student_name: str) -> str:
    """Handle general questions without tools"""
    
    history_text = ""
    if history:
        history_text = "CONVERSATION HISTORY:\n"
        for turn in history:
            history_text += f"User: {turn['user']}\nAssistant: {turn['assistant']}\n\n"
    
    system_prompt = f"""You are Success Coach AI, helping {student_name} with their academic journey.

This is a general question not about specific student data or platform features.

Provide helpful, encouraging advice based on the question. Be supportive and practical.

{history_text if history_text else "This is the start of the conversation."}
"""
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message)
    ]
    
    response = llm.invoke(messages).content
    return response


def _answer_student_question(llm, user_message: str, history: list[dict], tools_to_use: list, student_id: str, student_name: str) -> str:
    """Handle student data questions using appropriate tools"""
    
    tools_map = {
        "attendance": get_attendance_data,
        "scores": get_exam_scores,
        "schedule": get_exam_schedule,
        "profile": get_student_roster,
    }
    
    # Fetch data from all identified tools
    tool_results = {}
    for tool_name in tools_to_use:
        if tool_name in tools_map:
            try:
                result = tools_map[tool_name].invoke({"student_id": student_id})
                tool_results[tool_name] = result
            except Exception as e:
                tool_results[tool_name] = f"Error fetching {tool_name}: {str(e)}"
    
    # Format tool results
    tool_results_text = "\n\n".join([
        f"📌 {name.upper()}:\n{result}"
        for name, result in tool_results.items()
    ])
    
    # Create prompt with tool results
    history_text = ""
    if history:
        history_text = "CONVERSATION HISTORY:\n"
        for turn in history:
            history_text += f"User: {turn['user']}\nAssistant: {turn['assistant']}\n\n"
    
    system_prompt = f"""You are Success Coach AI helping {student_name} understand their academic performance.

You have fetched the following data for this student:

{tool_results_text}

---

Now answer the student's question using this data. Be specific with numbers and provide actionable insights.

{history_text if history_text else "This is the start of the conversation."}
"""
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message)
    ]
    
    response = llm.invoke(messages).content
    return response


def _answer_knowledge_base_question(user_message: str) -> str:
    """Handle knowledge base questions using RAG"""
    
    try:
        result = search_knowledge_base.invoke({"query": user_message})
        return result
    except Exception as e:
        print(f"❌ Error in _answer_knowledge_base_question: {str(e)}")
        import traceback
        traceback.print_exc()
        return f"I encountered an error while searching the knowledge base: {str(e)}"