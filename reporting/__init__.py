"""SprintNXT test execution reporting.

Enable it once in the root ``conftest.py``::

    pytest_plugins = ["reporting.plugin"]

Then, optionally, enrich tests and page objects::

    from reporting import tc, step, report, block

    @tc("REG-001", "Register with valid details", feature="Signup",
        types=["Functional", "Smoke"], expected="Registration Successful page is shown")
    def test_register(reg):
        report.data("email", email)
        with step("Submit the form"):
            ...
"""
from .collector import TestCollector, current, report, step
from .metadata import TEST_TYPES, block, tc

__all__ = ["tc", "step", "report", "block", "current", "TestCollector", "TEST_TYPES"]
