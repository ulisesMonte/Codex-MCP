"""
Interfaces package — abstractions for dependency inversion.

Only export protocols that exist in this repository; add new ABCs here as
concrete modules are introduced.
"""
from interfaces.agent import IAgent

__all__ = ["IAgent"]
