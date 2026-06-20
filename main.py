# At the end of main.py

import streamlit as st

page = st.sidebar.radio("Navigation", ["Student Chat", "Signal Dashboard"])

if page == "Student Chat":
    from UI.student_view import render_student_view
    render_student_view()
elif page == "Signal Dashboard":
    from UI.signal_dashboard import render_signal_dashboard
    render_signal_dashboard()