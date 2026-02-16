"""CLI entry point for obs-tasks."""

import click

from . import __version__


@click.group()
@click.version_option(version=__version__, prog_name="obs-tasks")
def cli():
    """Obsidian Task Automation — schedule and run tasks from your vault."""
    pass
