"""
Initial attempt on an integration test of packages/observer.py with the main
method and without mocking the span and patch_module variables or other methods.
"""

import os
import sys

import pytest

from packages import observer

# pylint: disable=protected-access


def test_no_tracing(capsys):
    """Test observer._init_tracing() of packages/observer.py"""

    # Prepare the environment and run the main method
    span, patch_module = run_main(capsys, config_dir="/sys")

    # assert that the noop tracing functions span and patch_module are not overridden
    assert span == observer.span_noop
    # pylint: disable-next=comparison-with-callable
    assert patch_module == observer.patch_module_noop


def test_tracing(capsys):
    """
    Test observer._init_tracing() and observer.main() from packages/observer.py

    The test directory contains a dummy `observer.conf` (currently empty)
    configuration file that is used to enable tracing for the test.

    As a result, observer._init_tracing() should:
    - not return the noop span and patch_module functions, but continue.
    - import the opentelemetry packages
    - read the configuration file
    - create a tracer
    - override the span and patch_module functions [checked by this test]
    - trace the script                             [not yet checked by this test]
    - run `observer_traced_script.py` as the traced script, which for now,
      just prints a message and exits with 0 [other exit codes not tested yet].
    - when the traced script exits, exist using its exit code [code for it in place]
    """

    # Prepare the environment and run the main method
    #
    # As config_dir, use the directory of this test file:
    #
    span, patch_module = run_main(capsys, config_dir=os.path.dirname(__file__))

    with capsys.disabled():
        # If this test fails in your environment, without any changes to the repo,
        # check for import errors from observer.py:_init_tracing() in the pytest logs.

        # Assert that the noop tracing functions span and patch_module are overridden
        assert span is not None and span != observer.span_noop
        # pylint: disable-next=comparison-with-callable
        assert patch_module is not None and patch_module != observer.patch_module_noop

        stdout = capsys.readouterr().out
        assert stdout == "Hello, I am a print() in tests/observer_traced_script.py.\n"


def run_main(capsys, config_dir):
    # Prepare the environment
    """Test observer._init_tracing() of packages/observer.py"""

    # Prepare the environment

    # Enable debug mode
    observer.DEBUG_ENABLED = True

    # Select the script to be traced for this test
    traced_script = f"{os.path.dirname(__file__)}/observer_traced_script.py"

    # Set the sys.argv to the script to be traced
    sys.argv = ["observer", traced_script]

    # Act
    configs = observer._get_configs_list(config_dir)
    span, patch_module = observer._init_tracing(configs, config_dir)
    with pytest.raises(SystemExit) as exc_info:
        observer.main()

    # Assert
    assert exc_info.type == SystemExit
    # 1 is returned by observer_traced_script.py's instrument_me().print():
    assert exc_info.value.code == 1

    # Return the span and patch_module for assertions by the test methods
    return span, patch_module
