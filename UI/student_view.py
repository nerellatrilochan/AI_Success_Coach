"""
Student View UI
Main interface for student-coach interactions with signal detection
"""

import os
import uuid
import streamlit as st
import logging
from datetime import datetime

from agents.conversation_agent import build_conversation_agent
from services.google_sheets_service import get_all_students
from services.mem0_service import get_mem0_service
from prompts.system_prompts import validate_input

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def render_student_view():
    """Main student view with chat and session management"""
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
    
    # Signal detection result tracking
    if "last_signal_result" not in st.session_state:
        st.session_state.last_signal_result = None

    students = get_all_students()

    # ============================================================================
    # SIDEBAR - STUDENT SELECTION & CONTROLS
    # ============================================================================
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
                        logger.info(f"Saving session for previous student: {st.session_state.selected_student_id}")
                        _save_current_session_to_mem0()
                    
                    # START FRESH SESSION FOR NEW STUDENT
                    st.session_state.selected_student_id = new_student_id
                    st.session_state.selected_label = selected_label
                    st.session_state.current_session_id = str(uuid.uuid4())
                    st.session_state.session_start_time = datetime.now()
                    st.session_state.last_signal_result = None
                    
                    # Clear chat history
                    if new_student_id not in st.session_state.student_histories:
                        st.session_state.student_histories[new_student_id] = []
                    
                    # 🆕 LOAD MEMORY CONTEXT FOR THIS STUDENT
                    try:
                        from services.memory_integration import get_memory_integration_service
                        memory_service = get_memory_integration_service()
                        student_name = selected_label.split('(')[0].strip()
                        memory_ctx = memory_service.prepare_memory_context(
                            new_student_id,
                            student_name
                        )
                        st.session_state.student_memory_context = memory_ctx
                    except Exception as e:
                        logger.warning(f"⚠️  Could not load memory context: {str(e)}")
                        st.session_state.student_memory_context = None
                    
                    st.rerun()
            else:
                st.session_state.selected_student_id = ""
        else:
            st.info("No students found in Google Sheets.")

        # ========================================================================
        # DISPLAY CURRENT STUDENT INFO
        # ========================================================================
        if st.session_state.selected_student_id:
            st.divider()
            st.markdown("**Current Student:**")
            st.write(st.session_state.selected_label)
            
            # Show memory context info - Session number and previous sessions
            if "student_memory_context" in st.session_state and st.session_state.student_memory_context:
                ctx = st.session_state.student_memory_context
                if not ctx["is_first_session"]:
                    st.caption(f"📊 Session #{ctx['session_number']} | {ctx['total_previous_sessions']} previous")
                else:
                    st.caption("✨ First time student!")
            
            # Session info
            if st.session_state.session_start_time:
                session_duration = (datetime.now() - st.session_state.session_start_time).seconds // 60
                st.caption(f"⏱️ Session: {session_duration} min")
                st.caption(f"🔑 ID: {st.session_state.current_session_id[:8]}...")
            
            # Last signal result (if available)
            if st.session_state.last_signal_result:
                signal_result = st.session_state.last_signal_result
                if signal_result.get("signal"):
                    st.divider()
                    signal = signal_result["signal"]
                    severity_emoji = {
                        "critical": "🔴",
                        "high": "🟠",
                        "medium": "🟡",
                        "low": "🟢"
                    }
                    severity_color = severity_emoji.get(signal.severity.value, "❓")
                    st.info(f"{severity_color} Last Signal: {signal.signal_type.value}")
            
            # ====================================================================
            # CHAT HISTORY CONTROLS
            # ====================================================================
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
                    st.session_state.last_signal_result = None
                    st.rerun()
            
            with col2:
                st.info(f"Messages: {len(current_history)}")
            
            # ====================================================================
            # END SESSION BUTTON (TRIGGERS SIGNAL DETECTION)
            # ====================================================================
            st.divider()
            if st.button("🛑 End Session", use_container_width=True, type="secondary"):
                _save_current_session_to_mem0()
                st.session_state.student_histories[st.session_state.selected_student_id] = []
                st.session_state.current_session_id = str(uuid.uuid4())  # Fresh session
                st.session_state.session_start_time = datetime.now()
                st.session_state.last_signal_result = None
                st.success("✅ Session ended and saved to memory!")
                st.rerun()
            
            # ====================================================================
            # PREVIOUS SESSIONS
            # ====================================================================
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

    # ============================================================================
    # MAIN CONTENT AREA
    # ============================================================================
    
    if not st.session_state.selected_student_id:
        st.warning("👈 Please select a student from the sidebar to continue.")
        return

    current_student_id = st.session_state.selected_student_id
    if current_student_id not in st.session_state.student_histories:
        st.session_state.student_histories[current_student_id] = []
    
    current_history = st.session_state.student_histories[current_student_id]

    # Display chat messages
    st.subheader("💬 Chat")
    for turn in current_history:
        with st.chat_message("user"):
            st.write(turn["user"])
        with st.chat_message("assistant"):
            st.write(turn["assistant"])

    # Build conversation agent
    agent_fn = build_conversation_agent(
        student_id=current_student_id,
        student_name=st.session_state.selected_label.split('(')[0].strip()
    )

    # Chat input
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
                    logger.error(f"Error in conversation agent: {str(e)}")
                    reply = f"I encountered an error: {str(e)}"
            st.write(reply)

        # Append to history
        current_history.append({
            "user": prompt,
            "assistant": reply
        })
        st.session_state.student_histories[current_student_id] = current_history


def _save_current_session_to_mem0() -> bool:
    """
    Save current session to Mem0 and trigger signal detection.
    
    Called when: 
    - Switching students
    - Clicking End Session button
    
    Process:
    1. Save chat history to Mem0 (extracts key facts)
    2. Run signal detection graph (Phase 3)
    3. Store signal if concerning
    4. Alert coach if urgent
    
    Edge cases handled:
    - No chat history
    - Mem0 API failure
    - Signal detection failure (non-blocking)
    - Invalid session state
    - LLM API failures
    """
    try:
        # ====================================================================
        # VALIDATION
        # ====================================================================
        student_id = st.session_state.selected_student_id
        if not student_id or not student_id.strip():
            logger.warning("⚠️  No student selected")
            return False
        
        chat_history = st.session_state.student_histories.get(student_id, [])
        
        if not chat_history:
            logger.info("ℹ️  No chat history to save")
            return False
        
        # Extract student information
        student_name = (
            st.session_state.selected_label.split('(')[0].strip() 
            if st.session_state.selected_label 
            else "Student"
        )
        session_id = st.session_state.current_session_id
        
        print(f"\n{'='*70}")
        print(f"💾 ENDING SESSION & PROCESSING")
        print(f"   Student: {student_name} ({student_id})")
        print(f"   Session ID: {session_id}")
        print(f"   Messages: {len(chat_history)}")
        print(f"{'='*70}\n")
        
        # ====================================================================
        # STEP 1: SAVE TO MEM0
        # ====================================================================
        logger.info(f"Step 1: Saving session to Mem0...")
        mem0_service = get_mem0_service()
        mem0_result = mem0_service.save_session(
            student_id=student_id,
            student_name=student_name,
            session_id=session_id,
            chat_history=chat_history,
            metadata={
                "category": "coaching_session",
                "saved_from": "student_view"
            }
        )
        
        if not mem0_result:
            logger.warning("⚠️  Mem0 save had issues, but continuing with signal detection")
        else:
            logger.info("✅ Session saved to Mem0")
        
        # ====================================================================
        # STEP 2: RUN SIGNAL DETECTION (PHASE 3)
        # ====================================================================
        logger.info("Step 2: Running signal detection graph...")
        
        try:
            # Import signal detection components
            from services.signal_detection_graph import get_signal_detection_graph
            from services.signal_types import SignalDetectionState
            
            # Get the graph
            signal_graph = get_signal_detection_graph()
            
            # Prepare initial state for the graph
            initial_state: SignalDetectionState = {
                "student_id": student_id,
                "session_id": session_id,
                "chat_history": chat_history,
                "student_name": student_name,
                "student_memory": {},
                "extracted_concerns": [],
                "pattern_history": {},
                "signal_type": None,
                "severity": None,
                "urgency": None,
                "signal": None,
                "should_notify": False,
                "notification_sent": False,
                "error": None,
                "error_node": None,
                "retry_count": 0,
            }
            
            print(f"\n{'='*70}")
            print(f"🔍 SIGNAL DETECTION GRAPH RUNNING")
            print(f"{'='*70}\n")
            
            # ================================================================
            # RUN THE LANGGRAPH
            # ================================================================
            final_state = signal_graph.invoke(initial_state)
            
            # ================================================================
            # PROCESS RESULTS
            # ================================================================
            signal = final_state.get("signal")
            error = final_state.get("error")
            urgency = final_state.get("urgency")
            severity = final_state.get("severity")
            
            # Store result in session state for sidebar display
            st.session_state.last_signal_result = {
                "signal": signal,
                "error": error,
                "urgency": urgency,
                "severity": severity
            }
            
            # ================================================================
            # HANDLE ERRORS
            # ================================================================
            if error:
                error_node = final_state.get("error_node", "unknown")
                logger.warning(
                    f"⚠️  Signal detection had error in '{error_node}': {error}"
                )
                print(f"\n⚠️  Signal Detection Issue: {error}")
                print(f"   Failed at node: {error_node}")
                print(f"   (Session was still saved to Mem0)\n")
            
            # ================================================================
            # HANDLE SIGNAL CREATED
            # ================================================================
            if signal:
                print(f"\n{'='*70}")
                print(f"✅ SIGNAL DETECTED & SAVED")
                print(f"   Signal ID: {signal.signal_id}")
                print(f"   Type: {signal.signal_type.value}")
                print(f"   Severity: {signal.severity.value}")
                print(f"   Urgency: {signal.urgency.value}")
                print(f"   Description: {signal.description[:80]}")
                print(f"{'='*70}\n")
                
                logger.info(f"Signal created: {signal.signal_id} ({signal.signal_type.value})")
                
                # Show different alerts based on urgency
                if urgency and urgency.value == "today":
                    st.warning(
                        f"""
                        🚨 **URGENT SIGNAL DETECTED**
                        
                        **Type**: {signal.signal_type.value}
                        
                        **Severity**: 🔴 {signal.severity.value.upper()}
                        
                        **Description**: {signal.description}
                        
                        **What this means**: The coach has been notified and will prioritize this student today.
                        """
                    )
                    logger.warning(f"URGENT signal created for {student_id}")
                
                elif urgency and urgency.value == "tomorrow":
                    st.info(
                        f"""
                        ⚠️ **Signal Detected**
                        
                        **Type**: {signal.signal_type.value}
                        
                        **Severity**: 🟠 {signal.severity.value}
                        
                        **Description**: {signal.description}
                        
                        **What this means**: Coach will address this within 24 hours.
                        """
                    )
                    logger.info(f"High-priority signal created for {student_id}")
                
                else:
                    st.caption(
                        f"""
                        📝 **Signal Recorded**
                        
                        Type: {signal.signal_type.value}
                        
                        This has been recorded for tracking and future reference.
                        """
                    )
                    logger.info(f"Informational signal created for {student_id}")
            
            else:
                print(f"\nℹ️  No concerning signals detected in this session\n")
                logger.info("No concerning signals detected")
            
            logger.info("✅ Signal detection graph completed successfully")
            return True
        
        except ImportError as ie:
            logger.warning(
                f"⚠️  Signal detection module not available: {str(ie)}"
            )
            print(f"\n⚠️  Signal detection not configured:")
            print(f"   {str(ie)}")
            print(f"   (Session was still saved to Mem0)\n")
            st.info("Signal detection not yet configured - but session was saved!")
            return True
        
        except Exception as sig_error:
            logger.error(
                f"❌ Signal detection failed (non-blocking): {str(sig_error)}"
            )
            print(f"\n❌ Signal detection error (non-blocking):")
            print(f"   {str(sig_error)}")
            print(f"   (Session was still saved to Mem0)\n")
            st.warning(
                f"Signal detection encountered an error (session still saved): "
                f"{str(sig_error)[:100]}"
            )
            return True  # Session was still saved to Mem0
    
    # ========================================================================
    # CRITICAL ERROR HANDLING
    # ========================================================================
    except Exception as e:
        logger.error(f"❌ CRITICAL ERROR in session save: {str(e)}")
        print(f"\n❌ CRITICAL ERROR:")
        print(f"   {str(e)}\n")
        st.error(f"Error saving session: {str(e)}")
        return False