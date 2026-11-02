"""Run unit tests and optionally TLC integration tests."""

import argparse
import unittest
from pathlib import Path

from tlc import TLCTestCase


def configure_tlc(suite: unittest.TestSuite, jar: Path | None) -> None:
    """Pass the explicit JAR path to each TLC test instance."""
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            configure_tlc(test, jar)
        elif isinstance(test, TLCTestCase):
            test.tla2tools_jar = jar


def main() -> int:
    """Parse test options and return the test suite's exit status."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tla2tools-jar", type=Path, help="Run TLC tests using this JAR"
    )
    args = parser.parse_args()
    if args.tla2tools_jar is not None and not args.tla2tools_jar.is_file():
        parser.error(f"TLA2TOOLS JAR does not exist: {args.tla2tools_jar}")
    suite = unittest.defaultTestLoader.discover(str(Path(__file__).resolve().parent))
    configure_tlc(suite, args.tla2tools_jar)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
