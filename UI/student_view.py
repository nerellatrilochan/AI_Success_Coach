import os
import streamlit as st
from agents.conversation_agent import build_conversation_agent
from services.google_sheets_service import get_all_students

def render_student_view():
    st.title("Success Coach AI")

    if "history" not in st.session_state:
        st.session_state.history = []

    if "selected_student_id" not in st.session_state:
        st.session_state.selected_student_id = ""

    students = get_all_students()

    with st.sidebar:
        st.subheader("Select Student")
        student_options = {
            f"{s['student_name']} ({s['student_id']})": s["student_id"]
            for s in students
        }

        if student_options:
            # Get list of labels
            student_labels = list(student_options.keys())
            
            # Initialize selected label if not set
            if "selected_label" not in st.session_state:
                st.session_state.selected_label = student_labels[0] if student_labels else None
            
            # Create selectbox with key to maintain state
            selected_label = st.selectbox(
                "Choose a student",
                options=student_labels,
                key="student_selector",
                index=student_labels.index(st.session_state.selected_label) if st.session_state.selected_label in student_labels else 0
            )
            
            # Guard the dictionary access
            if selected_label and selected_label in student_options:
                st.session_state.selected_student_id = student_options[selected_label]
                st.session_state.selected_label = selected_label
            else:
                st.session_state.selected_student_id = ""
        else:
            st.info("No students found in Google Sheets.")

        if st.button("Clear chat for this student"):
            st.session_state.history = []

    if not st.session_state.selected_student_id:
        st.warning("Please select a student from the sidebar to continue.")
        return

    for turn in st.session_state.history:
        with st.chat_message("user"):
            st.write(turn["user"])
        with st.chat_message("assistant"):
            st.write(turn["assistant"])

    agent_fn = build_conversation_agent(
        student_id=st.session_state.selected_student_id
    )

    if prompt := st.chat_input("Message your Success Coach..."):
        with st.chat_message("user"):
            st.write(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                reply = agent_fn(prompt, st.session_state.history)
            st.write(reply)

        st.session_state.history.append({
            "user": prompt,
            "assistant": reply
        })