"""Auto-instrumentation engine for service-layer functions.

Scans a package and wraps all public functions with LifecycleTracker.
Uses wrapt to preserve original function signatures and signatures.
"""

import fnmatch
import importlib
import inspect
import logging
import pkgutil
from typing import Callable

import wrapt

from app.core.observability import (
    LifecycleTracker,
    should_observe,
    observability_level,
    get_logger,
)

logger = logging.getLogger(__name__)


def _is_public_function(obj) -> bool:
    return (
        inspect.isfunction(obj)
        and not obj.__name__.startswith("_")
        and obj.__module__ is not None
    )


def _matches_any(name: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(name, p) for p in patterns)


def instrument_module(
    package_path: str,
    exclude: list[str] | None = None,
    compact_patterns: list[str] | None = None,
) -> int:
    """Auto-instrument all public functions in a package with LifecycleTracker.

    Args:
        package_path: Dotted package path, e.g. "app.services"
        exclude: Glob patterns for function names to skip
        compact_patterns: Glob patterns for functions that should use compact mode

    Returns:
        Number of functions instrumented
    """
    if observability_level() == "off":
        return 0

    if not should_observe(package_path):
        return 0

    exclude = exclude or []
    compact_patterns = compact_patterns or []

    try:
        package = importlib.import_module(package_path)
    except ImportError:
        logger.warning("instrument_module: cannot import %s", package_path)
        return 0

    count = 0
    package_dir = getattr(package, "__path__", None)
    if package_dir is None:
        return 0

    for importer, module_name, is_pkg in pkgutil.walk_packages(
        package_dir, prefix=package_path + "."
    ):
        if not should_observe(module_name):
            continue
        try:
            module = importlib.import_module(module_name)
        except (ImportError, SyntaxError, AttributeError) as e:
            logger.debug("instrument_module: skip %s (%s: %s)", module_name, type(e).__name__, e)
            continue

        for name, obj in inspect.getmembers(module, _is_public_function):
            if obj.__module__ != module_name:
                continue
            if _matches_any(name, exclude):
                continue
            if not should_observe(f"{module_name}.{name}"):
                continue

            compact = _matches_any(name, compact_patterns)
            span_name = f"{module_name.split('.')[-1]}.{name}"

            try:
                wrapper = LifecycleTracker(obj, span_name=span_name, compact=compact)
                setattr(module, name, wrapper)
                count += 1
            except Exception:
                logger.debug("instrument_module: failed to wrap %s.%s", module_name, name)

    log = get_logger("observability.instrument")
    log.info("Module_Instrumented", package=package_path, functions=count)
    return count
