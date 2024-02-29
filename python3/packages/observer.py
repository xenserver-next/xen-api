# Copyright (C) Cloud Software Group.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published
# by the Free Software Foundation; version 2.1 only. with the special
# exception on linking described in file LICENSE.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
"""
Calls the passed script with its original arguments, instrumenting it if at
least one *observer.conf file exists in the OBSERVER_CONFIG_DIR directory.

If there are no *observer.conf files or something fails, this script runs the
passed script without any instrumentation.
"""

import configparser
import functools
import inspect
import logging
import os
import runpy
import shlex
import sys
from datetime import datetime, timezone
from logging.handlers import SysLogHandler
from traceback import format_exc as exception
from typing import Any, List, Sequence, cast

# The opentelemetry library may generate exceptions we aren't expecting:
# But this code must not fail or it will cause the pass-through script to fail
# when at worst this script should be a noop. As such, we sometimes need to
# catch broad exceptions:
# pylint: disable=broad-exception-caught, too-many-locals, too-many-statements
# wrapt.decorator adds the extra parameters so we shouldn't provide them:
# pylint: disable=no-value-for-parameter, import-outside-toplevel

ENVVARS = "opentelemetry-python.readthedocs.io/en/latest/sdk/environment_variables.html"
DEFAULT_MODULES = "LVHDSR,XenAPI,SR,SRCommand,util"
DEBUG_ENABLED = False
FORMAT = "observer.py: %(message)s"
handler = SysLogHandler(facility="local5", address="/dev/log")
logging.basicConfig(format=FORMAT, handlers=[handler])
syslog = logging.getLogger(__name__)
if DEBUG_ENABLED:
    syslog.setLevel(logging.DEBUG)
else:
    syslog.setLevel(logging.INFO)
debug = syslog.debug


def _get_configs_list(config_dir):
    try:
        # There can be many observer config files in the configuration directory
        return [
            f"{config_dir}/{f}"
            for f in os.listdir(config_dir)
            if os.path.isfile(os.path.join(config_dir, f))
            and f.endswith("observer.conf")
        ]
    except FileNotFoundError as err:
        debug("configs exception: %s", err)
        return []


def read_config(config_path, header):
    """Read a config file and return a dictionary of key-value pairs."""

    parser = configparser.ConfigParser()
    with open(config_path, encoding="utf-8") as config_file:
        try:
            parser.read_string(f"[{header}]\n{config_file.read()}")
        except configparser.ParsingError as e:
            debug("read_config(): invalid config file %s: %s", config_path, e)
            return {}

    config = {k: v.strip("'") for k, v in dict(parser[header]).items()}
    debug("%s: %s", config_path, config)
    return config


def span_noop(wrapped=None, span_name_prefix=""):
    """Noop decorator, is overridden by _init_tracing() if there are configs."""

    if wrapped is None:
        return functools.partial(span_noop, span_name_prefix=span_name_prefix)

    return wrapped


def patch_module_noop(_):
    """Noop patch_module, is overridden by _init_tracing() if there are configs"""


def _init_tracing(configs: List[str], config_dir: str):  # NOSONAR(complexity=68)
    """Initialize tracing with the given configuration files.

    If configs is empty return the noop span and patch_module functions.
    If configs are passed:
    - import the opentelemetry packages
    - read the configuration file
    - create a tracer
    - trace the script
    - return the span and patch_module functions for tracing the program.
    """

    # Do not do anything unless configuration files have been found
    if not configs:
        return span_noop, patch_module_noop

    try:
        from warnings import simplefilter

        # On 3.10-3.12, the import of wrapt might trigger warnings, filter them:
        simplefilter(action="ignore", category=DeprecationWarning)
        import wrapt  # type: ignore[import-untyped]
        from opentelemetry import context, sdk, trace
        from opentelemetry.baggage.propagation import W3CBaggagePropagator
        from opentelemetry.exporter.zipkin.json import ZipkinExporter
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.trace.propagation.tracecontext import (
            TraceContextTextMapPropagator,
        )
    except ImportError as err:
        syslog.error("missing opentelemetry dependencies: %s", err)
        return span_noop, patch_module_noop

    try:
        config_dict = read_config(f"{config_dir}/all.conf", header="default")
    except FileNotFoundError:
        config_dict = {}

    module_names = config_dict.get("module_names", DEFAULT_MODULES).split(",")
    debug("module_names:%s", module_names)

    def create_tracer_from_config(path):
        """Create a tracer from a config file."""

        config = read_config(path, header=ENVVARS)
        cfg_opentelemetry_resource_attrs = config.get("otel_resource_attributes", "")

        if cfg_opentelemetry_resource_attrs:
            # opentelemetry requires some attributes,
            # e.g. service.name to be in the environment variable
            os.environ["OTEL_RESOURCE_ATTRIBUTES"] = cfg_opentelemetry_resource_attrs

        trace_log_dir = config.get("xs_exporter_bugtool_endpoint", "")

        zipkin_endpoints = config.get("xs_exporter_zipkin_endpoints")
        opentelemetry_exporter_zipkin_endpoints = (
            zipkin_endpoints.split(",") if zipkin_endpoints else []
        )
        opentelemetry_resource_attrs = dict(
            item.split("=")
            for item in config.get("otel_resource_attributes", "").split(",")
            if "=" in item
        )

        # rfc3339
        def get_new_output_filename():
            """Return an rfc3339-compliant ndjson file name."""

            service_name = config.get(
                "otel_service_name",
                opentelemetry_resource_attrs.get("service.name", "unknown"),
            )
            host_uuid = opentelemetry_resource_attrs.get("xs.host.uuid", "unknown")
            # Remove . to prevent users changing directories in the filename
            trace_state = os.getenv("TRACESTATE", "unknown").strip("'").replace(".", "")
            now = datetime.now(timezone.utc).isoformat()
            return (
                f"{trace_log_dir}/{service_name}-{host_uuid}-{trace_state}-{now}.ndjson"
            )

        # With the filename_callback parameter, this class can now be moved
        # outside of the function to the toplevel of _init_tracing module.
        # In this commit, the class is still inside the function to make it
        # easier to understand the changes.
        #
        # pylint: disable=too-few-public-methods
        class FileZipkinExporter(ZipkinExporter):
            """Class to export spans to a file in Zipkin format."""

            def __init__(self, *args, **kwargs):
                self.bugtool_filename_callback = kwargs.pop("filename_callback")
                self.bugtool_filename = self.bugtool_filename_callback()
                debug("bugtool filename=%s", self.bugtool_filename)
                self.bytes_written = 0
                super().__init__(*args, **kwargs)

            def export(
                self,
                spans: Sequence[trace.Span],  # type: ignore[override,no-any-unimported]
            ):
                """Export the given spans to the file endpoint."""

                data = self.encoder.serialize(spans, self.local_node)
                datastr = str(data)
                debug("data.type=%s,data.len=%s", type(data), len(datastr))
                debug("data=%s", datastr)
                os.makedirs(name=trace_log_dir, exist_ok=True)

                with open(self.bugtool_filename, "a", encoding="utf-8") as bugtool_file:
                    bugtool_file.write(f"{datastr}\n")  # ndjson

                # split file if it gets > 1MB
                self.bytes_written += len(data)
                if self.bytes_written > 1024 * 1024:
                    self.bugtool_filename = self.bugtool_filename_callback()
                    self.bytes_written = 0

                return sdk.trace.export.SpanExportResult.SUCCESS

        traceparent = os.getenv("TRACEPARENT", None)
        propagator = TraceContextTextMapPropagator()
        context_with_traceparent = propagator.extract({"traceparent": traceparent})

        context.attach(context_with_traceparent)

        # Create a tracer provider with the given resource attributes
        # and add a span processor for each zipkin endpoint

        provider = TracerProvider(
            resource=sdk.resources.Resource.create(
                cast(
                    dict[str, Any],  # cast dict[str, object] to dict[str, Any] for mypy
                    W3CBaggagePropagator().extract(
                        carrier={},  # context is expected to be Context():
                        context=context.Context(opentelemetry_resource_attrs),
                    ),
                )
            )
        )
        # Add a span processor for the file endpoint if trace_log_dir is
        # defined in the config file. The file endpoint is used for debugging
        # and is not intended for production use.
        # The file endpoint is used for debugging and is not intended for
        #
        if trace_log_dir:
            processor_file_zipkin = sdk.trace.export.BatchSpanProcessor(
                FileZipkinExporter(filename_callback=get_new_output_filename)
            )
            provider.add_span_processor(processor_file_zipkin)
        for zipkin_endpoint in opentelemetry_exporter_zipkin_endpoints:
            processor_zipkin = sdk.trace.export.BatchSpanProcessor(
                # https://opentelemetry-python.readthedocs.io/en/exporter/zipkin/zipkin.html
                ZipkinExporter(endpoint=zipkin_endpoint)
            )
            provider.add_span_processor(processor_zipkin)

        trace.set_tracer_provider(provider)
        return trace.get_tracer(__name__)

    tracers = list(map(create_tracer_from_config, configs))
    debug("tracers=%s", tracers)

    def span_of_tracers(wrapped=None, span_name_prefix=""):
        """
        Public decorator that creates a trace around a function func.

        If there are no tracers, the function is called without any tracing.
        If there are tracers, the function is called with a trace around it

        It also creates a span with the given span name prefix and then clones
        the returned span for each of the existing traces to produce a nested
        trace for each of them.

        Args:
            wrapped: The function to be traced.
            span_name_prefix: The prefix to be added to the span name.

        Returns:
            The decorated function or a partial function if wrapped is None.

        Example:

        @span_of_tracers(span_name_prefix="my_prefix")
        def my_function():
            pass

        my_function() will be traced with the span name "my_prefix:my_function"
        and the span will be cloned for each of the existing traces to produce
        a nested trace for each of them.

        If wrapped is None, the decorator is being used with parameters and
        a partial function is returned instead of the decorated function.
        """

        if wrapped is None:  # handle decorators with parameters
            return functools.partial(span_of_tracers, span_name_prefix=span_name_prefix)

        @wrapt.decorator
        def instrument_function(wrapped, _, args, kwargs):
            """Decorator that creates a trace around a function func."""

            if not tracers:
                return wrapped(*args, **kwargs)

            module_name = wrapped.__module__ if hasattr(wrapped, "__module__") else ""
            qual_name = wrapped.__qualname__ if hasattr(wrapped, "__qualname__") else ""

            if not module_name and not qual_name:
                span_name = str(wrapped)
            else:
                prefix = f"{span_name_prefix}:" if span_name_prefix else ""
                span_name = f"{prefix}{module_name}:{qual_name}"

            tracer = tracers[0]
            with tracer.start_as_current_span(span_name) as aspan:
                if inspect.isclass(wrapped):
                    # class or classmethod
                    aspan.set_attribute("xs.span.args.str", str(args))
                    aspan.set_attribute("xs.span.kwargs.str", str(kwargs))
                else:
                    # function, staticmethod or instance method
                    bound_args = inspect.signature(wrapped).bind(*args, **kwargs)
                    bound_args.apply_defaults()
                    for k, v in bound_args.arguments.items():
                        aspan.set_attribute(f"xs.span.arg.{k}", str(v))

                # must be inside "aspan" to produce nested trace
                result = wrapped(*args, **kwargs)

            return result

        def autoinstrument_class(aclass):
            """Auto-instrument a class."""

            t = tracers[0]
            module_name = f"{aclass.__module__}:{aclass.__qualname__}"

            with t.start_as_current_span(f"auto_instrumentation.add: {module_name}"):
                for method_name, method in aclass.__dict__.items():
                    if not callable(getattr(aclass, method_name)):
                        continue

                    with t.start_as_current_span(
                        f"class.instrument:{module_name}.{method_name}={method}"
                    ):
                        # Avoid RecursionError:
                        # maximum recursion depth exceeded in comparison
                        # in the XenAPI module (triggered by XMLRPC calls in it):
                        if method_name in ["__getattr__", "__call__", "__init__"]:
                            continue
                        try:
                            setattr(aclass, method_name, instrument_function(method))
                        except Exception:
                            debug("setattr.Wrapper: Exception %s", exception())

        def instrument_module(module):
            """Instrument the classes and functions in a module."""

            # instrument the methods of the classes in the module
            for _, class_obj in inspect.getmembers(module, predicate=inspect.isclass):
                try:
                    autoinstrument_class(class_obj)
                except Exception:
                    debug("Wrapper: Exception %s", exception())

            # instrument the module-level functions of the module
            for function, func_object in inspect.getmembers(module, inspect.isfunction):
                setattr(module, function, instrument_function(func_object))

        if inspect.ismodule(wrapped):
            instrument_module(wrapped)

        return instrument_function(wrapped)

    def _patch_module(module_name):
        wrapt.importer.discover_post_import_hooks(module_name)
        wrapt.importer.when_imported(module_name)(
            lambda hook: span_of_tracers(wrapped=hook)
        )

    for m in module_names:
        _patch_module(m)

    return span_of_tracers, _patch_module


observer_config_dir = os.getenv("OBSERVER_CONFIG_DIR", default=".").strip("'")
observer_configs = _get_configs_list(observer_config_dir)
debug("configs = %s", observer_configs)

try:
    # If there are configs, span and patch_module are now operational
    # and can be used to trace the program.
    # If there are no configs, or an exception is raised, span and patch_module
    # are not overridden and will be the defined no-op functions.

    # TODO: Please describe the purpose of patch_module and where it is called:
    # I could not find the mechanism that calls patch_module!
    # Is it called by wrapt.importer.when_imported() or so?
    # If not, it should be removed from the return value of _init_tracing,
    # and the no-op patch_module function should be removed as well:
    span, patch_module = _init_tracing(observer_configs, observer_config_dir)
except Exception as exc:
    syslog.error("Exception while setting up tracing, running script untraced: %s", exc)


def main():
    """
    Run the passed python script using the runpy module, passing the given arguments.

    The program will be automatically instrumented when the corresponding module
    in the program is imported.
    """

    # Shift all the argvs one left
    sys.argv = sys.argv[1:]
    argv0 = sys.argv[0]

    @span(span_name_prefix=argv0)
    def run(file):
        runpy.run_path(file, run_name="__main__")

    run(argv0)


if __name__ == "__main__":
    main()
