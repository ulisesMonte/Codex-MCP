"""
Interfaces package — Abstract Base Classes for all major components.

Dependency Inversion Principle: every module depends on these abstractions,
not on concrete implementations.
"""
from interfaces.agent import IAgent
from interfaces.llm_provider import ILLMProvider
from interfaces.renderer import ITemplateRenderer
from interfaces.validator import ICodeChecker
from interfaces.deployer import IDeployer
from interfaces.registry import IRegistry

__all__ = [
    "IAgent",
    "ILLMProvider",
    "ITemplateRenderer",
    "ICodeChecker",
    "IDeployer",
    "IRegistry",
]
