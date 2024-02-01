#!/usr/bin/env python
"""Test runner script to run the unit tests and run code coverage checks

It is used by the following:

- interactively to check the unit tests and coverage,
- by the pre-commit hooks pytest2 and pytest3 and
- by the GitHub Actions .github/workflows/main.yml

to:

- run the unit tests
- get code coverage and
- check the code coverage on the diff against master to be 100%.

Th need for it arises because:
- pre-commit does not support Python2 so in the GitHub Python2 matrix we need
  test runner that can run on both Python2 and Python3.

- Speed: It runs much faster than calling the individual commands because
  it runs them all in the same interpreter, which is far more efficient.

It reads the .pre-commit-config.yaml file to find the dependencies to install.
It installs the dependencies if not already installed.
It runs the unit tests and coverage using pytest.
It runs diff-cover to check the coverage against the master branch.
It returns 0 if the tests and diff-coverage pass, 1 otherwise.
"""
import os
import sys
from logging import basicConfig, fatal
from platform import python_version
from warnings import catch_warnings, simplefilter

import pytest
import yaml

try:
    from pip._internal.cli.main import main as pip_main
except ImportError:
    from pip import pip_main


try:
    from diff_cover.diff_cover_tool import main as diff_cover_main
except ImportError:
    from diff_cover.tool import diff_cover_main  # pyright: ignore[reportMissingImports]


def main():  # type:() -> int
    """Run the unit tests and coverage for Python2 or Python3

    Returns:
        int: 0 if the tests pass, 1 otherwise.
    """

    hooks = ["pytest3"] if sys.version_info[0] >= 3 else ["pytest2"]

    with open(".pre-commit-config.yaml", "rb") as file:
        pip_args = []
        for repo in yaml.safe_load(file).get("repos", []):
            for hook in repo.get("hooks", []):
                if hook.get("id") in hooks:
                    pip_args.extend(hook.get("additional_dependencies"))

    if not pip_args:
        sys.exit(0)
    if os.environ.get("PIP_INSTALL", None) != "done":
        if not pip_args:
            fatal("Could not find the dependencies to install for " + str(hooks))
            sys.exit(1)

        with catch_warnings():
            simplefilter(action="ignore", category=Warning)

            if pip_main(["install"] + pip_args) != 0:
                return 1

    pytest_args = [
        "--cov",
        "--cov-report=term-missing",
        "--cov-report=xml:.git/coverage" + python_version() + ".xml",
        "--cov-report=html:.git/cov_html" + python_version(),
        "--junitxml=.git/pytest" + python_version() + ".xml",
    ]
    os.environ["COVERAGE_FILE"] = ".git/.coverage" + python_version()
    if pytest.main(pytest_args) != 0:
        return 1

    diff_cover_args = [
        "diff-cover",
        "--compare-branch=origin/master",
        "--fail-under=100",
        ".git/coverage" + python_version() + ".xml",
    ]
    if python_version()[0] != "2":
        diff_cover_args += ["--ignore-whitespace", "--show-uncovered"]
    return diff_cover_main(diff_cover_args)


if __name__ == "__main__":
    os.environ["PYTHONDEVMODE"] = "yes"
    os.environ["PYTHONDONTWRITEBYTECODE"] = "yes"

    basicConfig(level="INFO")
    sys.exit(main())
