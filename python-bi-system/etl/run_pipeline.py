"""
etl/run_pipeline.py
===================
Master pipeline runner.

Executes all ETL layers in the correct order:
    Bronze → Silver → Gold

Each layer is imported and called in sequence.
A single DuckDB connection is opened and shared across all layers
so every table is visible to the next layer without file re-open.

Run from the project root:
    python etl/run_pipeline.py
"""

import logging
import sys
import time
from pathlib import Path

# Allow running from the project root or from inside the etl/ folder
sys.path.insert(0, str(Path(__file__).parent.parent))

from etl.bronze import get_connection, run as bronze_run, verify as bronze_verify

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def main() -> None:
    pipeline_start = time.time()

    log.info("╔══════════════════════════════════════════════════════════╗")
    log.info("║        DATA WAREHOUSE — PYTHON ETL PIPELINE             ║")
    log.info("╚══════════════════════════════════════════════════════════╝")

    con = get_connection()

    try:
        # ── Phase 1: Bronze ──────────────────────────────────────────
        bronze_run(con)
        bronze_ok = bronze_verify(con)
        if not bronze_ok:
            log.error("Pipeline halted: Bronze verification failed.")
            sys.exit(1)

        # ── Phase 2: Silver ──────────────────────────────────────────
        from etl.silver import run as silver_run, verify as silver_verify
        silver_run(con)
        silver_ok = silver_verify(con)
        if not silver_ok:
            log.error("Pipeline halted: Silver verification failed.")
            sys.exit(1)

        # ── Phase 3: Gold ────────────────────────────────────────────
        from etl.gold import run as gold_run, verify as gold_verify
        gold_run(con)
        gold_ok = gold_verify(con)
        if not gold_ok:
            log.error("Pipeline halted: Gold verification failed.")
            sys.exit(1)

        elapsed = time.time() - pipeline_start
        log.info("Pipeline completed in %.2f s", elapsed)

    finally:
        con.close()


if __name__ == "__main__":
    main()
