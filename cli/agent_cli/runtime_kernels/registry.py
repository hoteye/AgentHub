from __future__ import annotations

from collections.abc import Callable

from cli.agent_cli.runtime_kernels.base import KernelEngine, RuntimeKernel
from cli.agent_cli.runtime_kernels.errors import RuntimeKernelUnavailableError

KernelFactory = Callable[[], RuntimeKernel]


class RuntimeKernelRegistry:
    def __init__(self) -> None:
        self._factories: dict[KernelEngine, KernelFactory] = {}

    def register(self, engine: KernelEngine, factory: KernelFactory) -> None:
        self._factories[engine] = factory

    def unregister(self, engine: KernelEngine) -> None:
        self._factories.pop(engine, None)

    def has(self, engine: KernelEngine) -> bool:
        return engine in self._factories

    def create(self, engine: KernelEngine) -> RuntimeKernel:
        factory = self._factories.get(engine)
        if factory is None:
            raise RuntimeKernelUnavailableError(f"runtime kernel is not registered: {engine}")
        return factory()

    def engines(self) -> tuple[KernelEngine, ...]:
        return tuple(self._factories)


def build_default_registry() -> RuntimeKernelRegistry:
    from cli.agent_cli.runtime_kernels.agenthub_python.kernel import AgentHubPythonKernel

    registry = RuntimeKernelRegistry()
    registry.register("agenthub_python", AgentHubPythonKernel)
    return registry
