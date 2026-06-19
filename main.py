import streamlit as st
from UI.student_view import render_student_view

st.set_page_config(page_title="Success Coach AI", page_icon="🎓", layout="wide")

render_student_view()