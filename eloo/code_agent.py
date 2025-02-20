import os
import signal
from typing import Optional

from eloo.server.logger import eloo_logger as logger
from openhands.controller.state.state import State
from openhands.core.config import AppConfig, SandboxConfig
from openhands.core.main import create_runtime, run_controller
from openhands.events.action import MessageAction
from openhands.events.stream import EventStream
from openhands.runtime.base import Runtime

CONTAINER_NAME = 'openhands-test-container'


def handle_exit(signum, frame):
    """Handle exit signals without closing the container."""
    # Prevent runtime from being closed
    global _runtime
    if _runtime:
        _runtime._container = None  # type: ignore


# Register signal handlers
signal.signal(signal.SIGINT, handle_exit)
signal.signal(signal.SIGTERM, handle_exit)


class ExtendedSandboxConfig(SandboxConfig):
    """Extended sandbox config that allows setting container name."""

    container_name: str | None = None

    class Config:
        extra = 'allow'  # Allow extra fields to be passed through


class CodeAgent:
    """Manages the lifecycle of the OpenHands server and its Docker container."""

    def __init__(self):
        logger.debug('Initializing OpenHands server')
        self.runtime: Optional[Runtime] = None
        self.config: Optional[AppConfig] = None
        self._initialize_config()

    def _initialize_config(self):
        """Initialize the default configuration."""
        root_dir = os.path.dirname(os.path.dirname(__file__))
        workspace_dir = os.path.join(root_dir, 'workspace')
        os.makedirs(workspace_dir, exist_ok=True)

        sandbox_config = SandboxConfig(
            enable_auto_lint=True,
            use_host_network=False,
            timeout=300,
            platform='linux/amd64',
            keep_runtime_alive=True,
            rm_all_containers=False,
        )

        self.config = AppConfig(
            default_agent='CodeActAgent',
            run_as_openhands=False,
            runtime='docker',
            max_iterations=10,
            workspace_base=root_dir,
            workspace_mount_path='/Users/vigdor/GitHub/OpenHands/workspace',
            sandbox=sandbox_config,
            debug=False,
        )

    async def initialize(self):
        logger.debug('Connecting to OpenHands runtime')
        if self.config is None:
            raise ValueError('Config must be initialized before starting server')

        runtime = await get_or_create_runtime(self.config)
        self.runtime = runtime
        return self.runtime

    async def run_prompt(self, prompt: str):
        """Run a prompt using the initialized runtime."""
        if self.runtime is None:
            await self.initialize()

        return await run_agent_with_prompt(
            prompt=prompt, config=self.config, runtime=self.runtime
        )


async def get_or_create_runtime(config: AppConfig) -> Runtime:
    """Get existing runtime or create new one with consistent name."""
    global _runtime

    _runtime = create_runtime(config)
    await _runtime.connect()

    return _runtime


async def run_agent_with_prompt(
    prompt: str,
    config: Optional[AppConfig] = None,
    runtime: Optional[Runtime] = None,
) -> State:
    try:
        # Get event stream instance and clear subscribers
        event_stream = EventStream()
        event_stream.clear_subscribers()

        # Create the initial message action with our prompt
        initial_action = MessageAction(content=prompt)

        # Run the controller
        state = await run_controller(
            config=config,
            initial_user_action=initial_action,
            runtime=runtime,
            fake_user_response_fn=None,
            exit_on_message=True,
        )

        if state is None:
            raise ValueError('State should not be None.')

        return state
    finally:
        # Clean up subscribers after running
        event_stream.clear_subscribers()
