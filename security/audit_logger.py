#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import logging
import functools
import inspect
import traceback
from typing import Any, Callable, TypeVar, cast

# Configure the exir_architecture_tracer logger
logger = logging.getLogger("exir_architecture_tracer")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(levelname)s:%(name)s:%(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

F = TypeVar("F", bound=Callable[..., Any])

def exir_boundary_tracer(func: F) -> F:
    """
    Enterprise-grade decorator for systemic logging of inputs, outputs, and failures.
    Supports both synchronous and asynchronous functions.
    """
    func_name = f"{func.__module__}.{func.__qualname__}" if func.__module__ else func.__qualname__

    def format_args(*args: Any, **kwargs: Any) -> str:
        parts = []
        for i, arg in enumerate(args):
            parts.append(f"Positional_{i} ({type(arg).__name__}): {repr(arg)}")
        for k, v in kwargs.items():
            parts.append(f"Keyword_{k} ({type(v).__name__}): {repr(v)}")
        return " | ".join(parts) if parts else "None"

    @functools.wraps(func)
    async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
        arg_details = format_args(*args, **kwargs)
        logger.debug(f"🔑 [INPUT] Boundary Triggered: {func_name} | Values: {arg_details}")
        
        start_time = time.perf_counter()
        try:
            result = await func(*args, **kwargs)
            elapsed = (time.perf_counter() - start_time) * 1000.0
            ret_type = type(result).__name__
            logger.debug(f"🛡️ [OUTPUT] Boundary Resolved: {func_name} | Elapsed: {elapsed:.3f}ms | Return Type: {ret_type} | Return Value: {repr(result)}")
            return result
        except Exception as e:
            elapsed = (time.perf_counter() - start_time) * 1000.0
            exc_type = type(e).__name__
            logger.error(f"⚠️ [ERROR] Boundary Failed: {func_name} | Exception: {exc_type}: {str(e)} | Elapsed: {elapsed:.3f}ms | Trace: {traceback.format_exc().strip()}")
            raise

    @functools.wraps(func)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        arg_details = format_args(*args, **kwargs)
        logger.debug(f"🔑 [INPUT] Boundary Triggered: {func_name} | Values: {arg_details}")
        
        start_time = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            elapsed = (time.perf_counter() - start_time) * 1000.0
            ret_type = type(result).__name__
            logger.debug(f"🛡️ [OUTPUT] Boundary Resolved: {func_name} | Elapsed: {elapsed:.3f}ms | Return Type: {ret_type} | Return Value: {repr(result)}")
            return result
        except Exception as e:
            elapsed = (time.perf_counter() - start_time) * 1000.0
            exc_type = type(e).__name__
            logger.error(f"⚠️ [ERROR] Boundary Failed: {func_name} | Exception: {exc_type}: {str(e)} | Elapsed: {elapsed:.3f}ms | Trace: {traceback.format_exc().strip()}")
            raise

    if inspect.iscoroutinefunction(func):
        return cast(F, async_wrapper)
    return cast(F, sync_wrapper)
