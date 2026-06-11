#!/usr/bin/env python3
"""System Health Check - Convenience runner.

Usage: python run_healthcheck.py [options]
"""

from healthcheck.main import main
import sys

if __name__ == "__main__":
    sys.exit(main())
