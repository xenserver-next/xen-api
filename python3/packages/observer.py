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
        kvs_all_conf = {}
    module_names = kvs_all_conf.get(
        "module_names", "LVHDSR,XenAPI,SR,SRCommand,util"
    ).split(",")
    debug("module_names=%s", module_names)

    def tracer_of_config(path):
        otelvars = "opentelemetry-python.readthedocs.io/en/latest/sdk/environment_variables.html"
        argkv = kvs_of_config(path, header=otelvars)
        config_otel_resource_attributes = argkv.get("otel_resource_attributes", "")
        if config_otel_resource_attributes:
            # OTEL requires some attributes e.g. service.name to be in the environment variable
            os.environ["OTEL_RESOURCE_ATTRIBUTES"] = config_otel_resource_attributes
        trace_log_dir = argkv.get("xs_exporter_bugtool_endpoint", "")
        zipkin_endpoints = argkv.get("xs_exporter_zipkin_endpoints")
        otel_exporter_zipkin_endpoints = (
            zipkin_endpoints.split(",") if zipkin_endpoints else []
        )
        otel_resource_attributes = dict(
            item.split("=")
            for item in argkv.get("otel_resource_attributes", "").split(",")
            if "=" in item
        )
        service_name = argkv.get(
            "otel_service_name", otel_resource_attributes.get("service.name", "unknown")
        )

        host_uuid = otel_resource_attributes.get("xs.host.uuid", "unknown")
        # Remove . to prevent users changing directories in the bugtool_filenamer
        tracestate = os.getenv("TRACESTATE", "unknown").strip("'").replace(".", "")

        # rfc3339
        def bugtool_filenamer():
            """Compound function to return an rfc3339-compilant ndjson file name"""
            now = datetime.now(timezone.utc).isoformat()
            return (
                f"{trace_log_dir}/{service_name}-{host_uuid}-{tracestate}-{now}.ndjson"
            )

        # pylint: disable=too-few-public-methods
        class FileZipkinExporter(ZipkinExporter):
            """Class to export spans to a file in Zipkin format."""

            def __init__(self, *args, **kwargs):
                self.bugtool_filename = bugtool_filenamer()
                debug("bugtool filename=%s", self.bugtool_filename)
                self.written_so_far_in_file = 0
                super().__init__(*args, **kwargs)

            def export(self, spans: Sequence[Span]) -> SpanExportResult:
                """Export the given spans to the file endpoint."""
                data = self.encoder.serialize(spans, self.local_node)
                datastr = str(data)
                debug("data.type=%s,data.len=%s", type(data), len(datastr))
                debug("data=%s", datastr)
                os.makedirs(name=trace_log_dir, exist_ok=True)
                with open(self.bugtool_filename, "a", encoding="utf-8") as bugtool_file:
                    bugtool_file.write(f"{datastr}\n")  # ndjson
                self.written_so_far_in_file += len(data)
                if self.written_so_far_in_file > 1024 * 1024:
                    self.bugtool_filename = bugtool_filenamer()
                    self.written_so_far_in_file = 0
                return SpanExportResult.SUCCESS

        traceparent = os.getenv("TRACEPARENT", None)
        propagator = TraceContextTextMapPropagator()
        context_with_traceparent = propagator.extract({"traceparent": traceparent})

        context.attach(context_with_traceparent)

        # Create a tracer provider with the given resource attributes
        # and add a span processor for each zipkin endpoint

        provider = TracerProvider(
            resource=Resource.create(
                W3CBaggagePropagator().extract({}, otel_resource_attributes)
            )
        )
        if trace_log_dir:
            processor_filezipkin = BatchSpanProcessor(FileZipkinExporter())
            provider.add_span_processor(processor_filezipkin)
        for zipkin_endpoint in otel_exporter_zipkin_endpoints:
            processor_zipkin = BatchSpanProcessor(
                # https://opentelemetry-python.readthedocs.io/en/latest/exporter/zipkin/zipkin.html
                ZipkinExporter(endpoint=zipkin_endpoint)
            )
            provider.add_span_processor(processor_zipkin)

        trace.set_tracer_provider(provider)
        tracer = trace.get_tracer(__name__)
        return tracer

    tracers = list(map(tracer_of_config, configs))
    debug("tracers=%s", tracers)

    # Public decorator that creates a trace around a function func
    # and then clones the returned span for each of the existing traces.
    def span_of_tracers(wrapped=None, span_name_prefix=""):
        if wrapped is None:  # handle decorators with parameters
            return functools.partial(span_of_tracers, span_name_prefix=span_name_prefix)

        @wrapt.decorator
        def wrapper(wrapped, _, args, kwargs):
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
                    # function, staticmethod or instancemethod
                    bound_args = inspect.signature(wrapped).bind(*args, **kwargs)
                    bound_args.apply_defaults()
                    for k, v in bound_args.arguments.items():
                        aspan.set_attribute(f"xs.span.arg.{k}", str(v))
                # must be inside aspan to produce nested trace
                result = wrapped(*args, **kwargs)
            return result

        # wrapt.decorator adds the extra parameters so we shouldn't provide them
        # pylint: disable=no-value-for-parameter
        def autoinstrument_class(aclass):
            try:
                if inspect.isclass(aclass):
                    tracer = tracers[0]
                    my_module_name = f"{aclass.__module__}:{aclass.__qualname__}"
                    with tracer.start_as_current_span(
                        f"auto_instrumentation.add: {my_module_name}"
                    ):
                        for name in [
                            fn
                            for fn in aclass.__dict__
                            if callable(getattr(aclass, fn))
                        ]:
                            f = aclass.__dict__[name]
                            span_name = f"class.instrument:{my_module_name}.{name}={f}"
                            with tracer.start_as_current_span(span_name):
                                if name not in [
                                    "__getattr__",
                                    "__call__",
                                    "__init__",
                                ]:  # avoids python error 'maximum recursion depth exceeded
                                    # in comparison' in XenAPI
                                    try:
                                        setattr(aclass, name, wrapper(f))
                                    except Exception:
                                        debug(
                                            "setattr.Wrapper: Exception %s",
                                            traceback.format_exc(),
                                        )
            except Exception:
                debug("Wrapper: Exception %s", traceback.format_exc())

        def autoinstrument_module(amodule):
            classes = inspect.getmembers(amodule, inspect.isclass)
            for _, aclass in classes:
                autoinstrument_class(aclass)
            functions = inspect.getmembers(amodule, inspect.isfunction)
            for function_name, afunction in functions:
                setattr(amodule, function_name, wrapper(afunction))

        if inspect.ismodule(wrapped):
            autoinstrument_module(wrapped)

        return wrapper(wrapped)

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
    span, patch_module = _init_tracing(observer_configs, observer_config_dir)
except Exception as exc:
    syslog.error("Exception while setting up tracing, running script as noop: %s", exc)


def main():
    """
    Run a program passed as parameter, with its original arguments so that there's no need to
    manually decorate the program. The program will be forcibly instrumented by patch_module
    above when the corresponding module in program is imported.
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
