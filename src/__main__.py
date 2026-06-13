# ──────────────────────────────────────────────────────────────
# Gmail Draft Agent — Entry Point
# Run with: python -m src
# ──────────────────────────────────────────────────────────────

import argparse
import logging
import sys
import os

# Load .env file for local development (no-op if python-dotenv not installed or .env missing)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src.agent import run_agent


def main():
    parser = argparse.ArgumentParser(description="Gmail Customer Query Draft Agent")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without creating drafts or applying labels (testing mode).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug-level logging.",
    )
    args = parser.parse_args()

    # ── Configure logging ─────────────────────────────────────
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if args.dry_run:
        logging.getLogger().info("🔒 DRY RUN MODE — no drafts will be created, no labels applied.")

    try:
        stats = run_agent(dry_run=args.dry_run)

        # Exit with code 0 on success, even if some individual emails had errors
        if stats["errors"] > 0:
            logging.getLogger().warning(f"{stats['errors']} email(s) had processing errors.")

        sys.exit(0)

    except Exception as e:
        logging.getLogger().error(f"Agent run failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
