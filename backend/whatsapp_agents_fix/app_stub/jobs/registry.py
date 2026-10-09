"""FAKE stand-in for the real app's job registry -- just enough for
jobs/handlers.py (the real, patched file) to import and define its
handlers as plain callables."""


def job_handler(name):
    def decorator(fn):
        return fn
    return decorator
