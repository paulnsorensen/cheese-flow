"""Deterministic helpers consumed by cheese-flow agents and skills.

Tools here are tiny, pure-where-possible Python modules that agents shell out
to instead of running raw `git log`/`grep`/etc. and burning context tokens
on the parser. Each tool ships with pytest tests and is wired into a real
caller. No speculative tooling.
"""
