"""
Initialize signals database
Run once to create schema
"""

import sys
sys.path.append('..')

from services.signal_storage_service import SignalStorageService

if __name__ == "__main__":
    print("Initializing signals database...")
    service = SignalStorageService()
    print("✅ Database initialized successfully")
    print(f"Database path: chroma_db/signals.sqlite3")