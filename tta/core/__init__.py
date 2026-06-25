"""Toolkit-agnostic analysis core (SDD §5.1, ADR-0002).

Nothing in here may import from the UI or CLI adapter packages;
the boundary is CI-enforced (SDD §5.2).
"""
