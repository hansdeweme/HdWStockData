# GitHub configuration

The Package checks workflow runs offline package tests, builds the wheel and
source distribution, and validates their metadata on Linux and Windows with
Python 3.11 and 3.13. Showcase GUI tests require additional optional dependencies
and are not included in this workflow.

PyPI publishing is not enabled. Configure a release workflow and PyPI trusted
publishing when the package is ready for its first release.
