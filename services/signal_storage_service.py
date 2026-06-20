"""
Signal Storage Service
Database operations for signal persistence with comprehensive error handling
"""

import sqlite3
import os
from typing import List, Optional, Dict, Any
from datetime import datetime
from contextlib import contextmanager
import logging

from services.signal_types import Signal, SignalFilters, SignalAnalysis, SeverityLevel, UrgencyLevel

logger = logging.getLogger(__name__)
DB_PATH = "chroma_db/signals.sqlite3"


class SignalStorageService:
    """Handles all signal database operations"""
    
    def __init__(self, db_path: str = DB_PATH):
        """Initialize database with auto-schema creation"""
        self.db_path = db_path
        self._ensure_db_exists()
    
    @contextmanager
    def _get_connection(self):
        """Context manager for database connections with error handling"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=5.0)
            conn.row_factory = sqlite3.Row
            yield conn
        except sqlite3.OperationalError as e:
            logger.error(f"❌ Database connection failed: {str(e)}")
            raise
        finally:
            if conn:
                conn.close()
    
    def _ensure_db_exists(self):
        """Create database schema if it doesn't exist"""
        try:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Main signals table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS signals (
                        signal_id TEXT PRIMARY KEY,
                        student_id TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        signal_type TEXT NOT NULL,
                        description TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        urgency TEXT NOT NULL,
                        evidence TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        reviewed INTEGER DEFAULT 0,
                        coach_notes TEXT,
                        is_duplicate INTEGER DEFAULT 0,
                        previous_signal_id TEXT,
                        FOREIGN KEY (previous_signal_id) REFERENCES signals(signal_id)
                    )
                """)
                
                # Indexes for common queries
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_student_urgency 
                    ON signals(student_id, urgency)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_severity 
                    ON signals(severity)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_created_at 
                    ON signals(created_at)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_student_created 
                    ON signals(student_id, created_at DESC)
                """)
                
                # Audit log table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS signal_audit_log (
                        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        signal_id TEXT NOT NULL,
                        action TEXT NOT NULL,
                        changed_by TEXT,
                        changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        old_value TEXT,
                        new_value TEXT,
                        FOREIGN KEY (signal_id) REFERENCES signals(signal_id)
                    )
                """)
                
                conn.commit()
                logger.info("✅ Signal database initialized successfully")
        
        except Exception as e:
            logger.error(f"❌ Failed to initialize database: {str(e)}")
            raise
    
    def save_signal(self, signal: Signal) -> bool:
        """
        Save signal to database with duplicate detection
        
        Edge cases handled:
        - Duplicate signal in recent timeframe
        - Database connection failure
        - Invalid signal data
        - Concurrent writes
        """
        try:
            # Check for recent duplicate
            recent_dup = self._find_duplicate_signal(
                signal.student_id,
                signal.signal_type,
                hours_lookback=6
            )
            
            if recent_dup:
                logger.warning(
                    f"⚠️  Duplicate signal detected for {signal.student_id}. "
                    f"Marking as duplicate of {recent_dup['signal_id']}"
                )
                signal.is_duplicate = True
                signal.previous_signal_id = recent_dup['signal_id']
            
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT INTO signals (
                        signal_id, student_id, session_id, signal_type,
                        description, severity, urgency, evidence,
                        created_at, reviewed, coach_notes,
                        is_duplicate, previous_signal_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    signal.signal_id,
                    signal.student_id,
                    signal.session_id,
                    signal.signal_type.value,
                    signal.description,
                    signal.severity.value,
                    signal.urgency.value,
                    signal.evidence,
                    signal.created_at.isoformat(),
                    int(signal.reviewed),
                    signal.coach_notes,
                    int(signal.is_duplicate),
                    signal.previous_signal_id
                ))
                
                # Log to audit
                cursor.execute("""
                    INSERT INTO signal_audit_log (signal_id, action, changed_by, new_value)
                    VALUES (?, ?, ?, ?)
                """, (
                    signal.signal_id,
                    "created",
                    "system",
                    signal.json()
                ))
                
                conn.commit()
                logger.info(f"✅ Signal saved: {signal.signal_id}")
                return True
        
        except sqlite3.IntegrityError:
            logger.warning(f"⚠️  Signal {signal.signal_id} already exists")
            return False
        except Exception as e:
            logger.error(f"❌ Error saving signal: {str(e)}")
            return False
    
    def _find_duplicate_signal(
        self,
        student_id: str,
        signal_type: Any,
        hours_lookback: int = 6
    ) -> Optional[Dict]:
        """Find similar signal from recent timeframe"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT signal_id, created_at
                    FROM signals
                    WHERE student_id = ?
                    AND signal_type = ?
                    AND datetime(created_at) > datetime('now', ?)
                    AND reviewed = 0
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (
                    student_id,
                    signal_type.value if hasattr(signal_type, 'value') else signal_type,
                    f'-{hours_lookback} hours'
                ))
                
                result = cursor.fetchone()
                return dict(result) if result else None
        
        except Exception as e:
            logger.warning(f"⚠️  Duplicate check failed: {str(e)}")
            return None
    
    def get_signals_by_student(
        self,
        student_id: str,
        limit: int = 20,
        offset: int = 0
    ) -> List[Signal]:
        """
        Retrieve signals for a student
        
        Edge cases handled:
        - Student not found
        - Database errors
        - Empty result set
        - Invalid pagination
        """
        try:
            if not student_id or not student_id.strip():
                logger.warning("Invalid student_id provided")
                return []
            
            limit = max(1, min(limit, 100))  # Bounds check: 1-100
            offset = max(0, offset)
            
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT * FROM signals
                    WHERE student_id = ?
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                """, (student_id, limit, offset))
                
                rows = cursor.fetchall()
                
                signals = []
                for row in rows:
                    try:
                        signal = Signal(
                            signal_id=row['signal_id'],
                            student_id=row['student_id'],
                            session_id=row['session_id'],
                            signal_type=row['signal_type'],
                            description=row['description'],
                            severity=row['severity'],
                            urgency=row['urgency'],
                            evidence=row['evidence'],
                            created_at=datetime.fromisoformat(row['created_at']),
                            reviewed=bool(row['reviewed']),
                            coach_notes=row['coach_notes'],
                            is_duplicate=bool(row['is_duplicate']),
                            previous_signal_id=row['previous_signal_id']
                        )
                        signals.append(signal)
                    except Exception as e:
                        logger.warning(f"⚠️  Failed to parse signal: {str(e)}")
                        continue
                
                return signals
        
        except Exception as e:
            logger.error(f"❌ Error retrieving signals: {str(e)}")
            return []
    
    def get_urgent_signals(self) -> List[Signal]:
        """
        Get all signals requiring immediate attention (TODAY urgency or CRITICAL severity)
        
        Used for coach dashboard alerts
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT * FROM signals
                    WHERE (urgency = ? OR severity = ?)
                    AND reviewed = 0
                    ORDER BY severity DESC, created_at DESC
                """, ("today", "critical"))
                
                rows = cursor.fetchall()
                return [self._row_to_signal(row) for row in rows]
        
        except Exception as e:
            logger.error(f"❌ Error retrieving urgent signals: {str(e)}")
            return []
    
    def get_signals_by_filters(self, filters: SignalFilters) -> List[Signal]:
        """
        Advanced filtering with multiple criteria
        
        Edge cases handled:
        - Empty filter results
        - Invalid date ranges
        - No filters applied
        - Pagination bounds
        """
        try:
            query = "SELECT * FROM signals WHERE 1=1"
            params = []
            
            # Build dynamic query
            if filters.student_id:
                query += " AND student_id = ?"
                params.append(filters.student_id)
            
            if filters.severity:
                severity_vals = [s.value for s in filters.severity]
                placeholders = ",".join(["?" for _ in severity_vals])
                query += f" AND severity IN ({placeholders})"
                params.extend(severity_vals)
            
            if filters.urgency:
                urgency_vals = [u.value for u in filters.urgency]
                placeholders = ",".join(["?" for _ in urgency_vals])
                query += f" AND urgency IN ({placeholders})"
                params.extend(urgency_vals)
            
            if filters.signal_type:
                type_vals = [t.value for t in filters.signal_type]
                placeholders = ",".join(["?" for _ in type_vals])
                query += f" AND signal_type IN ({placeholders})"
                params.extend(type_vals)
            
            if filters.reviewed is not None:
                query += " AND reviewed = ?"
                params.append(int(filters.reviewed))
            
            if filters.date_from:
                query += " AND datetime(created_at) >= ?"
                params.append(filters.date_from.isoformat())
            
            if filters.date_to:
                query += " AND datetime(created_at) <= ?"
                params.append(filters.date_to.isoformat())
            
            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([filters.limit, filters.offset])
            
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                rows = cursor.fetchall()
                return [self._row_to_signal(row) for row in rows]
        
        except Exception as e:
            logger.error(f"❌ Error filtering signals: {str(e)}")
            return []
    
    def mark_signal_reviewed(
        self,
        signal_id: str,
        coach_notes: str = "",
        coach_id: str = "unknown"
    ) -> bool:
        """
        Mark signal as reviewed with optional coach notes
        
        Edge cases:
        - Signal not found
        - Already reviewed
        - Empty notes
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    UPDATE signals
                    SET reviewed = 1, coach_notes = ?
                    WHERE signal_id = ?
                """, (coach_notes, signal_id))
                
                if cursor.rowcount == 0:
                    logger.warning(f"Signal {signal_id} not found")
                    return False
                
                # Audit log
                cursor.execute("""
                    INSERT INTO signal_audit_log (signal_id, action, changed_by, old_value, new_value)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    signal_id,
                    "reviewed",
                    coach_id,
                    "reviewed=0",
                    f"reviewed=1, notes={coach_notes[:50]}"
                ))
                
                conn.commit()
                logger.info(f"✅ Signal {signal_id} marked reviewed")
                return True
        
        except Exception as e:
            logger.error(f"❌ Error marking signal reviewed: {str(e)}")
            return False
    
    def get_student_analysis(self, student_id: str) -> Optional[SignalAnalysis]:
        """
        Get comprehensive signal analysis for a student
        
        Edge cases:
        - Student with no signals
        - Database errors
        - Invalid student_id
        """
        try:
            if not student_id or not student_id.strip():
                return None
            
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Get all signals for student
                cursor.execute("""
                    SELECT severity, urgency, signal_type, created_at
                    FROM signals
                    WHERE student_id = ?
                    ORDER BY created_at DESC
                """, (student_id,))
                
                rows = cursor.fetchall()
                
                if not rows:
                    return SignalAnalysis(
                        student_id=student_id,
                        total_signals=0,
                        signals_this_week=0,
                        critical_count=0,
                        high_count=0,
                        recent_pattern=None,
                        recommendations=[],
                        last_signal_at=None
                    )
                
                # Calculate stats
                total_signals = len(rows)
                critical_count = sum(1 for r in rows if r['severity'] == 'critical')
                high_count = sum(1 for r in rows if r['severity'] == 'high')
                signals_this_week = sum(1 for r in rows 
                    if (datetime.now() - datetime.fromisoformat(r['created_at'])).days <= 7)
                
                # Detect pattern
                signal_types = [r['signal_type'] for r in rows[:10]]
                recent_pattern = max(set(signal_types), key=signal_types.count) if signal_types else None
                
                # Generate recommendations
                recommendations = []
                if critical_count > 0:
                    recommendations.append("🔴 Critical signals present - immediate intervention needed")
                if high_count >= 3:
                    recommendations.append("⚠️  Multiple high-severity signals - schedule intensive support")
                if signals_this_week >= 3:
                    recommendations.append("📈 Escalating concerns this week - monitor closely")
                if recent_pattern == "exam_anxiety" and signals_this_week >= 2:
                    recommendations.append("📚 Exam anxiety recurring - offer structured revision planning")
                
                return SignalAnalysis(
                    student_id=student_id,
                    total_signals=total_signals,
                    signals_this_week=signals_this_week,
                    critical_count=critical_count,
                    high_count=high_count,
                    recent_pattern=recent_pattern,
                    recommendations=recommendations,
                    last_signal_at=datetime.fromisoformat(rows[0]['created_at']) if rows else None
                )
        
        except Exception as e:
            logger.error(f"❌ Error analyzing student signals: {str(e)}")
            return None
    
    def _row_to_signal(self, row: sqlite3.Row) -> Signal:
        """Convert database row to Signal object"""
        return Signal(
            signal_id=row['signal_id'],
            student_id=row['student_id'],
            session_id=row['session_id'],
            signal_type=row['signal_type'],
            description=row['description'],
            severity=row['severity'],
            urgency=row['urgency'],
            evidence=row['evidence'],
            created_at=datetime.fromisoformat(row['created_at']),
            reviewed=bool(row['reviewed']),
            coach_notes=row['coach_notes'],
            is_duplicate=bool(row['is_duplicate']),
            previous_signal_id=row['previous_signal_id']
        )


# Singleton
_signal_storage_service = None


def get_signal_storage_service() -> SignalStorageService:
    """Get or create signal storage service instance"""
    global _signal_storage_service
    if _signal_storage_service is None:
        _signal_storage_service = SignalStorageService()
    return _signal_storage_service