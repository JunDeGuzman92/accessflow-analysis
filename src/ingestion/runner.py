"""Runner for the ingestion scheduler."""

import asyncio
import os
import signal
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.ingestion.scheduler import IngestionScheduler


def main():
    """Run the ingestion scheduler."""
    check_interval = int(os.environ.get("CHECK_INTERVAL_HOURS", "24"))
    data_dir = Path(os.environ.get("DATA_DIR", "data"))

    scheduler = IngestionScheduler(data_dir=data_dir, check_interval_hours=check_interval)

    print(f"Starting ingestion scheduler (check every {check_interval}h)")
    print(f"Data directory: {data_dir}")

    running = True

    def signal_handler(sig, frame):
        nonlocal running
        print("\nShutting down...")
        running = False

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    while running:
        try:
            if scheduler.should_check():
                df = scheduler.run_check()
                if df is not None:
                    print(f"Processed {len(df)} restrictions")
            else:
                print("Not time to check yet.")

            # Sleep in small increments to allow graceful shutdown
            for _ in range(60):
                if not running:
                    break
                import time
                time.sleep(1)

        except Exception as e:
            print(f"Error: {e}")
            import time
            time.sleep(60)

    print("Scheduler stopped.")


if __name__ == "__main__":
    main()
