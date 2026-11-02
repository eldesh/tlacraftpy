"""Shared setup for tests that invoke TLC."""

import unittest
from pathlib import Path


class TLCTestCase(unittest.TestCase):
    """Receive the JAR path explicitly from the test runner."""

    tla2tools_jar: Path | None = None

    def setUp(self) -> None:
        if self.tla2tools_jar is None:
            self.skipTest("run make test TLA2TOOLS_JAR=/path/to/tla2tools.jar for TLC")
