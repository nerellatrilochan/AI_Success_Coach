import os
import uuid
import streamlit as st
from datetime import datetime
from agents.conversation_agent import build_conversation_agent
from services.google_sheets_service import get_all_students
from services.mem0_service import get_mem0_service
from prompts.system_prompts import validate_input

def render_student_view():
    st.title("Success Coach AI 🎓")
    st.markdown("Your personal AI-powered academic success coach")

    # Initialize session state for multi-student support
    if "student_histories" not in st.session_state:
        st.session_state.student_histories = {}

    if "selected_student_id" not in st.session_state:
        st.session_state.selected_student_id = ""

    if "selected_label" not in st.session_state:
        st.session_state.selected_label = ""
    
    # Session tracking
    if "current_session_id" not in st.session_state:
        st.session_state.current_session_id = str(uuid.uuid4())
    
    if "session_start_time" not in st.session_state:
        st.session_state.session_start_time = None

    students = get_all_students()

    with st.sidebar:
        st.subheader("👤 Select Student")
        student_options = {
            f"{s['student_name']} ({s['student_id']})": s["student_id"]
            for s in students
        }

        if student_options:
            student_labels = list(student_options.keys())
            
            if not st.session_state.selected_label and student_labels:
                st.session_state.selected_label = student_labels[0]
            
            selected_label = st.selectbox(
                "Choose a student",
                options=student_labels,
                key="student_selector",
                index=student_labels.index(st.session_state.selected_label) 
                    if st.session_state.selected_label in student_labels else 0
            )
            
            # Detect student change
            if selected_label and selected_label in student_options:
                new_student_id = student_options[selected_label]
                
                if new_student_id != st.session_state.selected_student_id:
                    # Save previous session if exists
                    if st.session_state.selected_student_id:
                        _save_current_session_to_mem0()
                    
                    # Start fresh session for new student
                    st.session_state.selected_student_id = new_student_id
                    st.session_state.selected_label = selected_label
                    st.session_state.current_session_id = str(uuid.uuid4())  # NEW SESSION
                    st.session_state.session_start_time = datetime.now()
                    
                    # Clear current student's chat history when switching
                    if new_student_id not in st.session_state.student_histories:
                        st.session_state.student_histories[new_student_id] = []
                    
                    st.rerun()
            else:
                st.session_state.selected_student_id = ""
        else:
            st.info("No students found in Google Sheets.")

        # Display current student info
        if st.session_state.selected_student_id:
            st.divider()
            st.markdown("**Current Student:**")
            st.write(st.session_state.selected_label)
            
            # Session info
            if st.session_state.session_start_time:
                session_duration = (datetime.now() - st.session_state.session_start_time).seconds // 60
                st.caption(f"⏱️ Session: {session_duration} min")
                st.caption(f"🔑 ID: {st.session_state.current_session_id[:8]}...")
            
            # Chat history
            st.divider()
            st.subheader("Chat History")
            
            current_history = st.session_state.student_histories.get(
                st.session_state.selected_student_id, 
                []
            )
            
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("🗑️ Clear Chat", use_container_width=True):
                    if st.session_state.selected_student_id in st.session_state.student_histories:
                        del st.session_state.student_histories[st.session_state.selected_student_id]
                    st.rerun()
            
            with col2:
                st.info(f"Messages: {len(current_history)}")
            
            # NEW: End Session Button
            st.divider()
            if st.button("🛑 End Session", use_container_width=True, type="secondary"):
                _save_current_session_to_mem0()
                st.session_state.student_histories[st.session_state.selected_student_id] = []
                st.session_state.current_session_id = str(uuid.uuid4())  # Fresh session
                st.session_state.session_start_time = datetime.now()
                st.success("✅ Session ended and saved to memory!")
                st.rerun()
            
            # Previous sessions
            st.divider()
            st.subheader("📚 Previous Sessions")
            
            if st.button("🔄 Load Sessions", use_container_width=True):
                mem0_service = get_mem0_service()
                previous_sessions = mem0_service.get_session_history(
                    student_id=st.session_state.selected_student_id,
                    limit=10
                )
                
                if previous_sessions:
                    st.success(f"✅ Found {len(previous_sessions)} session(s)")
                    with st.expander("View Sessions", expanded=True):
                        for i, session in enumerate(previous_sessions, 1):
                            metadata = session.get("metadata", {})
                            timestamp = metadata.get("session_ended_at", "N/A")
                            msg_count = metadata.get("message_count", "N/A")
                            memory_text = session.get("memory", "")[:100]
                            
                            st.markdown(f"""
**Session {i}** - {timestamp}
- 💬 Messages: {msg_count}
- 📝 Summary: {memory_text}...
                            """)
                else:
                    st.info("No previous sessions. Start chatting!")

    if not st.session_state.selected_student_id:
        st.warning("👈 Please select a student from the sidebar to continue.")
        return

    current_student_id = st.session_state.selected_student_id
    if current_student_id not in st.session_state.student_histories:
        st.session_state.student_histories[current_student_id] = []
    
    current_history = st.session_state.student_histories[current_student_id]

    st.subheader("💬 Chat")
    for turn in current_history:
        with st.chat_message("user"):
            st.write(turn["user"])
        with st.chat_message("assistant"):
            st.write(turn["assistant"])

    agent_fn = build_conversation_agent(
        student_id=current_student_id,
        student_name=st.session_state.selected_label.split('(')[0].strip()
    )

    if prompt := st.chat_input("Message your Success Coach..."):
        is_valid, error_message = validate_input(prompt)
        if not is_valid:
            st.error(f"⚠️ {error_message}")
            st.stop()
        
        with st.chat_message("user"):
            st.write(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    reply = agent_fn(prompt, current_history)
                except Exception as e:
                    reply = f"I encountered an error: {str(e)}"
            st.write(reply)

        current_history.append({
            "user": prompt,
            "assistant": reply
        })
        st.session_state.student_histories[current_student_id] = current_history


def _save_current_session_to_mem0() -> bool:
    """
    Save current session to Mem0.
    Called when: Switching students OR clicking End Session button.
    """
    try:
        student_id = st.session_state.selected_student_id
        if not student_id:
            return False
        
        chat_history = st.session_state.student_histories.get(student_id, [])
        
        if not chat_history:
            print("⚠️  No chat history to save")
            return False
        
        # Extract student name
        student_name = st.session_state.selected_label.split('(')[0].strip() if st.session_state.selected_label else "Student"
        session_id = st.session_state.current_session_id
        
        # Save to Mem0
        mem0_service = get_mem0_service()
        result = mem0_service.save_session(
            student_id=student_id,
            student_name=student_name,
            session_id=session_id,
            chat_history=chat_history,
            metadata={
                "category": "coaching_session",
                "saved_from": "student_view"
            }
        )
        
        return result is not None
    
    except Exception as e:
        print(f"❌ Error saving session: {str(e)}")
        return False