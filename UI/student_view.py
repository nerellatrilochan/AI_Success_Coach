import os
import streamlit as st
from agents.conversation_agent import build_conversation_agent
from services.google_sheets_service import get_all_students
from prompts.system_prompts import validate_input

def render_student_view():
    st.title("Success Coach AI 🎓")
    st.markdown("Your personal AI-powered academic success coach")

    # Initialize session state for multi-student support
    if "student_histories" not in st.session_state:
        st.session_state.student_histories = {}  # {student_id: [history]}

    if "selected_student_id" not in st.session_state:
        st.session_state.selected_student_id = ""

    if "selected_label" not in st.session_state:
        st.session_state.selected_label = ""

    students = get_all_students()

    with st.sidebar:
        st.subheader("👤 Select Student")
        student_options = {
            f"{s['student_name']} ({s['student_id']})": s["student_id"]
            for s in students
        }

        if student_options:
            student_labels = list(student_options.keys())
            
            # Initialize selected label if not set
            if not st.session_state.selected_label and student_labels:
                st.session_state.selected_label = student_labels[0]
            
            # Create selectbox
            selected_label = st.selectbox(
                "Choose a student",
                options=student_labels,
                key="student_selector",
                index=student_labels.index(st.session_state.selected_label) 
                    if st.session_state.selected_label in student_labels else 0
            )
            
            # CRITICAL FIX: Detect student change and clear history
            if selected_label and selected_label in student_options:
                new_student_id = student_options[selected_label]
                
                # If student changed, load their history
                if new_student_id != st.session_state.selected_student_id:
                    st.session_state.selected_student_id = new_student_id
                    st.session_state.selected_label = selected_label
                    st.rerun()  # Rerun to refresh the UI with new student's history
            else:
                st.session_state.selected_student_id = ""
        else:
            st.info("No students found in Google Sheets.")

        # Display current student info
        if st.session_state.selected_student_id:
            st.divider()
            st.markdown("**Current Student:**")
            st.write(st.session_state.selected_label)
            
            # History management
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

    if not st.session_state.selected_student_id:
        st.warning("👈 Please select a student from the sidebar to continue.")
        return

    # Get current student's history
    current_student_id = st.session_state.selected_student_id
    if current_student_id not in st.session_state.student_histories:
        st.session_state.student_histories[current_student_id] = []
    
    current_history = st.session_state.student_histories[current_student_id]

    # Display conversation history
    st.subheader("💬 Chat")
    for turn in current_history:
        with st.chat_message("user"):
            st.write(turn["user"])
        with st.chat_message("assistant"):
            st.write(turn["assistant"])

    # Build agent for current student
    agent_fn = build_conversation_agent(
        student_id=current_student_id,
        student_name=st.session_state.selected_label.split('(')[0].strip()
    )

    # Chat input
    if prompt := st.chat_input("Message your Success Coach..."):
        # Validate input with guardrails
        is_valid, error_message = validate_input(prompt)
        if not is_valid:
            st.error(f"⚠️ {error_message}")
            st.stop()
        
        # Display user message
        with st.chat_message("user"):
            st.write(prompt)

        # Generate response
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    reply = agent_fn(prompt, current_history)
                except Exception as e:
                    reply = f"I encountered an error: {str(e)}"
            st.write(reply)

        # Add to current student's history
        current_history.append({
            "user": prompt,
            "assistant": reply
        })
        st.session_state.student_histories[current_student_id] = current_history