"""Process-level runtime hooks (avoids circular imports from GraphQL → main)."""
from typing import Callable, List

_reload_hooks: List[Callable[[], None]] = []


def register_reload_hook(hook: Callable[[], None]) -> None:
    """Register a callback invoked after config.yaml is saved."""
    _reload_hooks.append(hook)


def trigger_config_reload() -> None:
    """Notify listeners that connectors/config should be reloaded."""
    for hook in list(_reload_hooks):
        try:
            hook()
        except Exception as exc:
            print(f"Config reload hook failed: {exc}")
