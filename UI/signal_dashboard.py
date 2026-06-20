"""
Signal Dashboard
Coach interface for viewing and managing signals
Scaffold for Phase 4 development
"""

import streamlit as st
from datetime import datetime, timedelta
from typing import List

from services.signal_storage_service import get_signal_storage_service
from services.signal_types import SignalFilters, SeverityLevel, UrgencyLevel


def render_signal_dashboard():
    """
    Render the signal dashboard for coaches
    
    Features:
    - View urgent signals
    - Filter by severity/urgency
    - Mark signals as reviewed
    - See student analysis
    - Trend analysis
    """
    st.set_page_config(page_title="Signal Dashboard", page_icon="🚨", layout="wide")
    
    st.title("🚨 Signal Dashboard")
    st.markdown("Real-time concerns detected from student sessions")
    
    storage = get_signal_storage_service()
    
    # ============================================================
    # SECTION 1: URGENT SIGNALS AT A GLANCE
    # ============================================================
    st.header("🔴 Urgent Alerts (Today)")
    
    urgent_signals = storage.get_urgent_signals()
    
    if urgent_signals:
        for signal in urgent_signals:
            col1, col2, col3 = st.columns([0.7, 0.2, 0.1])
            
            with col1:
                st.markdown(f"""
                **{signal.student_id}** | {signal.signal_type.value}
                
                {signal.description}
                
                Evidence: {signal.evidence[:100]}...
                """)
            
            with col2:
                severity_color = {
                    "critical": "🔴",
                    "high": "🟠",
                    "medium": "🟡",
                    "low": "🟢"
                }
                st.write(f"{severity_color.get(signal.severity.value, '❓')} {signal.severity.value}")
            
            with col3:
                if st.button("✓", key=f"review_{signal.signal_id}"):
                    storage.mark_signal_reviewed(signal.signal_id)
                    st.rerun()
        
        st.divider()
    else:
        st.success("✅ No urgent signals right now")
    
    # ============================================================
    # SECTION 2: FILTER & SEARCH
    # ============================================================
    st.header("🔍 Search & Filter")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        search_student = st.text_input("Student ID")
    with col2:
        filter_severity = st.multiselect(
            "Severity",
            options=[s.value for s in SeverityLevel],
            default=["critical", "high"]
        )
    with col3:
        filter_urgency = st.multiselect(
            "Urgency",
            options=[u.value for u in UrgencyLevel],
            default=["today"]
        )
    
    # Execute filter
    if st.button("Search"):
        filters = SignalFilters(
            student_id=search_student if search_student else None,
            severity=[SeverityLevel(s) for s in filter_severity] if filter_severity else None,
            urgency=[UrgencyLevel(u) for u in filter_urgency] if filter_urgency else None,
        )
        
        results = storage.get_signals_by_filters(filters)
        
        st.write(f"Found {len(results)} signal(s)")
        for signal in results:
            with st.expander(f"{signal.student_id} - {signal.signal_type.value}"):
                st.json({
                    "id": signal.signal_id,
                    "severity": signal.severity.value,
                    "urgency": signal.urgency.value,
                    "created": signal.created_at.isoformat(),
                    "description": signal.description,
                    "evidence": signal.evidence,
                    "reviewed": signal.reviewed
                })
    
    # ============================================================
    # SECTION 3: STUDENT ANALYSIS
    # ============================================================
    st.header("📊 Student Analysis")
    
    student_id = st.text_input("Enter Student ID for analysis")
    
    if student_id:
        analysis = storage.get_student_analysis(student_id)
        
        if analysis:
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Total Signals", analysis.total_signals)
            with col2:
                st.metric("This Week", analysis.signals_this_week)
            with col3:
                st.metric("🔴 Critical", analysis.critical_count)
            with col4:
                st.metric("🟠 High", analysis.high_count)
            
            if analysis.recent_pattern:
                st.info(f"**Recent Pattern**: {analysis.recent_pattern}")
            
            if analysis.recommendations:
                st.warning("**Recommendations:**")
                for rec in analysis.recommendations:
                    st.write(f"• {rec}")
        else:
            st.info(f"No signals found for student {student_id}")


if __name__ == "__main__":
    render_signal_dashboard()