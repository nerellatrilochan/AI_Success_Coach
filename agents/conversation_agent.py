from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from config.llm import get_llm
from services.google_sheets_service import get_student_profile
import json

SYSTEM_PROMPT = """
You are Success Coach AI, an intelligent assistant designed to support college and university students with their academic success.

Your mission is to help students excel academically, professionally, and personally.

CORE RESPONSIBILITIES:
1. Answer questions about student-specific data (attendance, exam scores, exams, profile)
2. Provide academic guidance and study tips
3. Help with career planning and professional development
4. Offer time management and productivity advice
5. Support skill development and learning

AVAILABLE TOOLS:
You have access to four tools that fetch real student data from the spreadsheet:
- get_attendance_data: Fetches detailed attendance records (weeks, classes attended/scheduled, percentages)
- get_exam_scores_data: Fetches exam results (subjects, scores, percentages, dates)
- get_exam_schedule_data: Fetches upcoming exam information (subjects, dates, exam types)
- get_student_roster_data: Fetches basic student information (name, program, cohort, manager email)

WHEN TO USE TOOLS:
Use these tools ONLY when the student asks questions that require data from the spreadsheet:
- Attendance-related: "What's my attendance?", "Which week did I attend the least?", "What's my attendance percentage?", "How many classes have I missed?", "Am I absent too much?"
- Exam scores-related: "What are my marks?", "How did I score in maths?", "What's my average?", "Which subject am I strong in?", "Where am I weak?", "What's my percentage?"
- Exam schedule-related: "When are my exams?", "What's my exam date?", "Do I have any upcoming exams?", "When is my next test?"
- Profile-related: "Who is my manager?", "What's my program?", "What's my cohort?", "Tell me about myself"

WHEN NOT TO USE TOOLS:
Do NOT use tools for general questions unrelated to this specific student's data:
- "Explain recursion", "How to study?", "Tips for time management"
- These should be answered directly without calling tools

TOOL DATA ANALYSIS:
Once you get data from the tools, analyze it deeply to answer complex questions:
- For "Which week did I attend the least?" → Analyze attendance records and find the minimum
- For "In which subject am I strong?" → Analyze exam scores and find highest percentage
- For "What's my weak area?" → Analyze exam scores and find lowest percentage
- For "Average attendance?" → Calculate percentage across all weeks
- For "Average score?" → Calculate average across all subjects

BEHAVIOR RULES:
1. Always provide specific numbers and data from the tools when answering about student data
2. Be honest if data is missing or unavailable
3. Give actionable insights based on the data (e.g., "You attended 70% of classes in week 2, you should focus on attendance")
4. For general academic questions, provide comprehensive guidance even without using tools
5. Never invent data - only use what comes from the tools

Your primary goal is to help each student understand their performance and guide them toward success.
"""

def get_attendance_data_impl(student_id_param: str) -> str:
    """Fetch the student's attendance record."""
    profile = get_student_profile(student_id_param)
    attendance = profile.get("attendance", [])
    
    if not attendance:
        return "No attendance data available."
    
    output = ["DETAILED ATTENDANCE RECORD:"]
    for record in attendance:
        week = record.get('week_of', 'N/A')
        attended = record.get('classes_attended', 0)
        scheduled = record.get('classes_scheduled', 0)
        pct = record.get('attendance_pct', 'N/A')
        output.append(f"  Week of {week}: {attended}/{scheduled} classes ({pct}%)")
    
    # Calculate overall statistics
    try:
        total_attended = sum(int(r.get('classes_attended', 0)) for r in attendance if r.get('classes_attended', ''))
        total_scheduled = sum(int(r.get('classes_scheduled', 0)) for r in attendance if r.get('classes_scheduled', ''))
        overall_pct = (total_attended / total_scheduled * 100) if total_scheduled > 0 else 0
        output.append(f"\n  OVERALL: {total_attended}/{total_scheduled} classes ({overall_pct:.1f}%)")
    except:
        pass
    
    return "\n".join(output)

def get_exam_scores_data_impl(student_id_param: str) -> str:
    """Fetch the student's exam scores and marks."""
    profile = get_student_profile(student_id_param)
    exam_scores = profile.get("exam_scores", [])
    
    if not exam_scores:
        return "No exam scores available."
    
    output = ["EXAM SCORES AND MARKS:"]
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
        
        output.append(f"\n  STATISTICS:")
        output.append(f"    Average Score: {avg_pct:.1f}%")
        output.append(f"    Highest Score: {max_pct}%")
        output.append(f"    Lowest Score: {min_pct}%")
        
        # Find strongest and weakest subjects
        strongest = exam_scores[percentages.index(max_pct)]['subject']
        weakest = exam_scores[percentages.index(min_pct)]['subject']
        output.append(f"    Strongest Subject: {strongest} ({max_pct}%)")
        output.append(f"    Weakest Subject: {weakest} ({min_pct}%)")
    
    return "\n".join(output)

def get_exam_schedule_data_impl(student_id_param: str) -> str:
    """Fetch the student's upcoming exam schedule."""
    profile = get_student_profile(student_id_param)
    exam_schedule = profile.get("exam_schedule", [])
    
    if not exam_schedule:
        return "No upcoming exams scheduled."
    
    output = [f"UPCOMING EXAMS ({len(exam_schedule)} total):"]
    for exam in exam_schedule:
        subject = exam.get('subject', 'N/A')
        date = exam.get('exam_date', 'N/A')
        exam_type = exam.get('exam_type', 'N/A')
        output.append(f"  • {subject}: {date} ({exam_type})")
    
    return "\n".join(output)

def get_student_roster_data_impl(student_id_param: str) -> str:
    """Fetch the student's basic profile information."""
    profile = get_student_profile(student_id_param)
    roster = profile.get("roster", {})
    
    if not roster:
        return "No student roster data available."
    
    output = [
        "STUDENT PROFILE:",
        f"  Name: {roster.get('name', 'N/A')}",
        f"  Student ID: {roster.get('student_id', 'N/A')}",
        f"  Program: {roster.get('program', 'N/A')}",
        f"  Cohort: {roster.get('cohort', 'N/A')}",
        f"  Manager Email: {roster.get('manager_email', 'N/A')}",
    ]
    
    return "\n".join(output)

def build_conversation_agent(*, student_id: str = "", student_name: str = ""):
    """Build a ReAct-style agent that intelligently calls tools based on student questions."""
    
    llm = get_llm()
    
    # Define tools that the agent can use
    tools = [
        {
            "name": "get_attendance_data",
            "description": "Fetch the student's attendance record including weekly breakdown and overall attendance percentage",
            "function": get_attendance_data_impl
        },
        {
            "name": "get_exam_scores_data",
            "description": "Fetch the student's exam scores, marks, percentages, and analysis of strong/weak subjects",
            "function": get_exam_scores_data_impl
        },
        {
            "name": "get_exam_schedule_data",
            "description": "Fetch the student's upcoming exam schedule with dates and exam types",
            "function": get_exam_schedule_data_impl
        },
        {
            "name": "get_student_roster_data",
            "description": "Fetch the student's basic profile information (name, program, cohort, manager)",
            "function": get_student_roster_data_impl
        }
    ]
    
    def run(user_message: str, history: list[dict]) -> str:
        """Run the agent with the user message and history."""
        
        # Format history for context
        history_text = ""
        if history:
            history_text = "CONVERSATION HISTORY:\n"
            for turn in history:
                history_text += f"User: {turn['user']}\nAssistant: {turn['assistant']}\n\n"
        
        # Create tool descriptions for the LLM
        tool_descriptions = "\n".join([
            f"- {tool['name']}: {tool['description']}"
            for tool in tools
        ])
        
        # Create comprehensive input for the agent
        system_with_tools = f"""{SYSTEM_PROMPT}

AVAILABLE TOOLS:
{tool_descriptions}

---

STUDENT ID: {student_id}

{history_text if history_text else "This is the start of the conversation."}

---

CURRENT USER MESSAGE: {user_message}

Remember:
1. Analyze the user's question carefully
2. Determine if it requires fetching data using tools
3. Call the appropriate tool(s) if needed by mentioning them
4. Analyze the returned data to answer complex questions
5. Provide specific numbers and insights
6. For general questions, answer directly without tools

If you need to use a tool, mention it clearly like: "Let me fetch your attendance data..." then provide the tool name.
"""
        
        try:
            # First LLM call to determine if tools are needed
            messages = [SystemMessage(content=system_with_tools)]
            
            for turn in history:
                messages.append(HumanMessage(content=turn["user"]))
                messages.append(AIMessage(content=turn["assistant"]))
            
            messages.append(HumanMessage(content=user_message))
            
            response = llm.invoke(messages).content
            
            # Check if the response mentions any tools
            tool_names = [tool["name"] for tool in tools]
            tool_results = {}
            
            for tool in tools:
                if tool["name"].lower() in response.lower() or any(keyword in response.lower() for keyword in tool["description"].lower().split()):
                    # Call the tool
                    result = tool["function"](student_id)
                    tool_results[tool["name"]] = result
                    response = response.replace(f"[{tool['name']}]", result)
            
            # If tools were called, make a second call with the tool results
            if tool_results:
                tool_results_text = "\n\n".join([
                    f"Tool '{name}' returned:\n{result}"
                    for name, result in tool_results.items()
                ])
                
                messages = [SystemMessage(content=system_with_tools)]
                
                for turn in history:
                    messages.append(HumanMessage(content=turn["user"]))
                    messages.append(AIMessage(content=turn["assistant"]))
                
                messages.append(HumanMessage(content=user_message))
                messages.append(AIMessage(content=response))
                messages.append(HumanMessage(content=f"Here are the tool results:\n\n{tool_results_text}\n\nNow please provide a comprehensive answer to the student's question using this data."))
                
                response = llm.invoke(messages).content
            
            return response
            
        except Exception as e:
            return f"I apologize, but I encountered an error: {str(e)}"
    
    return run