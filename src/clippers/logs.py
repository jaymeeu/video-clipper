"""Logging setup for the programs clippers runs as: the CLI and the API worker.

Library modules only *emit* records (logger = logging.getLogger(__name__)); the program's
entry point calls configure_logging once to decide what's shown and how.
"""

import logging


def configure_logging(*, verbose: bool, timestamps: bool = False) -> None:
    """Normal: our own INFO messages, plus only warnings from libraries. Verbose: everything.

    Loggers form a tree by dotted name, so the "clippers" level covers clippers.video,
    clippers.transcribe, etc., while httpx/faster_whisper/... inherit the root's level.
    `timestamps` suits long-running processes (the worker); the CLI leaves them out.
    """
    fmt = "%(levelname)s %(name)s: %(message)s"
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format=f"%(asctime)s {fmt}" if timestamps else fmt,
        datefmt="%H:%M:%S",
        force=True,  # replace any handlers left over from a previous config
    )
    logging.getLogger("clippers").setLevel(logging.DEBUG if verbose else logging.INFO)
