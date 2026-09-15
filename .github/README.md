# GitHub configuration

The Package checks workflow runs offline package and showcase contract tests, builds the wheel and
source distribution, and validates their metadata on Linux and Windows with
Python 3.11 and 3.13. Showcase GUI tests require additional optional dependencies
and are skipped when those dependencies are unavailable.

A separate Windows/Python 3.13 job installs the showcase extra and runs the
offscreen GUI tests and synthetic chart compatibility checks.

The package has been published to PyPI. Automated PyPI publishing from GitHub
is not configured; the workflow above only tests and builds distributions.
