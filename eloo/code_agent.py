import asyncio
import os
import signal
from typing import Optional
from dataclasses import dataclass, field
from pydantic import BaseModel
from eloo.server.logger import logger

from openhands.core.config import AppConfig, SandboxConfig
from openhands.core.main import create_runtime, run_controller
from openhands.events.action import MessageAction
from openhands.controller.state.state import State
from openhands.runtime.base import Runtime
from openhands.utils.async_utils import call_async_from_sync
import docker

CONTAINER_NAME = "openhands-test-container"


def handle_exit(signum, frame):
    """Handle exit signals without closing the container."""
    print("\nExiting without stopping container...")
    # Prevent runtime from being closed
    global _runtime
    if _runtime:
        _runtime._container = None  # type: ignore
    exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, handle_exit)
signal.signal(signal.SIGTERM, handle_exit)

class ExtendedSandboxConfig(SandboxConfig):
    """Extended sandbox config that allows setting container name."""
    container_name: str | None = None

    class Config:
        extra = "allow"  # Allow extra fields to be passed through

class CodeAgent:
    """Manages the lifecycle of the OpenHands server and its Docker container."""
    
    def __init__(self):
        logger.debug("Initializing OpenHands server")
        self.runtime: Optional[Runtime] = None
        self.config: Optional[AppConfig] = None
        self._initialize_config()
    
    def _initialize_config(self):
        """Initialize the default configuration."""
        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        workspace_dir = os.path.join(root_dir, "workspace")
        os.makedirs(workspace_dir, exist_ok=True)
        
        sandbox_config = ExtendedSandboxConfig(
            enable_auto_lint=True,
            use_host_network=False,
            timeout=300,
            platform="linux/amd64",
            container_name=CONTAINER_NAME,
            keep_runtime_alive=True,
            rm_all_containers=False,
        )
        
        self.config = AppConfig(
            default_agent="CodeActAgent",
            run_as_openhands=False,
            runtime=os.environ.get("RUNTIME", "docker"),
            max_iterations=10,
            workspace_base=root_dir,
            workspace_mount_path="/Users/vigdor/GitHub/OpenHands/workspace",
            sandbox=sandbox_config,
            debug=True,
        )

    async def initialize(self):
        logger.debug("Connecting to OpenHands runtime")
        """Initialize the server by setting up the Docker container without running a command."""
        if self.config is None:
            raise ValueError("Config must be initialized before starting server")
            
        self.runtime = await get_or_create_runtime(self.config)
        return self.runtime

    async def run_prompt(self, prompt: str) -> State:
        """Run a prompt using the initialized runtime."""
        if self.runtime is None:
            await self.initialize()
            
        return await run_agent_with_prompt(
            prompt=prompt,
            config=self.config,
            runtime=self.runtime
        )

async def get_or_create_runtime(config: AppConfig) -> Runtime:
    """Get existing runtime or create new one with consistent name."""
    global _runtime
    
    docker_client = docker.from_env()
    
    # Check if our container already exists
    try:
        container = docker_client.containers.get(CONTAINER_NAME)
        if container.status != "running":
            container.start()
        print(f"Reusing existing container: {CONTAINER_NAME}")
        _runtime = create_runtime(config)
        # Set the existing container directly
        _runtime._container = container  # type: ignore
        await _runtime.connect()
    except docker.errors.NotFound:
        print(f"Creating new container: {CONTAINER_NAME}")
        _runtime = create_runtime(config)
        await _runtime.connect()
        
        # Debug the runtime and container
        print(f"Runtime type: {type(_runtime)}")
        if hasattr(_runtime, '_container'):
            container = getattr(_runtime, '_container')
            print(f"Container: {container}")
            print(f"Container ID: {container.id if container else 'None'}")
            print(f"Container status: {container.status if container else 'None'}")
            
            try:
                # Try to rename with error handling
                container.rename(CONTAINER_NAME)
                print(f"Successfully renamed container to {CONTAINER_NAME}")
            except Exception as e:
                print(f"Error renaming container: {str(e)}")
                # Try to get container ID if possible
                try:
                    print(f"Container details: {container.attrs}")
                except Exception as inner_e:
                    print(f"Could not get container details: {str(inner_e)}")
        else:
            print("Runtime has no _container attribute")
            print(f"Runtime attributes: {dir(_runtime)}")
    
    return _runtime

async def run_agent_with_prompt(
    prompt: str,
    config: Optional[AppConfig] = None,
    runtime: Optional[Runtime] = None,
) -> State:
    """Run an OpenHands agent with a specific prompt.
    
    Args:
        prompt: The prompt/instruction to send to the agent
        config: Optional AppConfig. If not provided, uses default settings
        runtime: Optional Runtime. If not provided, creates a new one
        
    Returns:
        The final State after the agent completes
    """
    if config is None:
        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        workspace_dir = os.path.join(root_dir, "workspace")
        os.makedirs(workspace_dir, exist_ok=True)
        
        # Create sandbox config with only the fields we want to override
        sandbox_config = ExtendedSandboxConfig(
            enable_auto_lint=True,
            use_host_network=False,
            timeout=300,
            platform="linux/amd64",
            container_name=CONTAINER_NAME,
            keep_runtime_alive=True,  # Keep container alive between runs
            rm_all_containers=False,  # Don't remove containers automatically
        )
        
        config = AppConfig(
            default_agent="CodeActAgent",
            run_as_openhands=False,
            runtime=os.environ.get("RUNTIME", "docker"),
            max_iterations=10,
            workspace_base=root_dir,
            workspace_mount_path="/Users/vigdor/GitHub/OpenHands/workspace",
            sandbox=sandbox_config,
            debug=True,
        )

    if runtime is None:
        runtime = await get_or_create_runtime(config)

    try:
        # Create the initial message action with our prompt
        initial_action = MessageAction(content=prompt)
        
        # Run the controller - note we await here instead of using asyncio.run()
        state = await run_controller(
            config=config,
            initial_user_action=initial_action,
            runtime=runtime,
            fake_user_response_fn=None,
            exit_on_message=False,
        )

        if state is None:
            raise ValueError('State should not be None.')

        return state

    finally:
        # Don't close the runtime - we want to reuse it
        pass


def get_user_prompt() -> str:
    """Get multi-line input from the user."""
    print("Enter your prompt (type '/done' on a new line when finished):")
    lines = []
    while True:
        line = input()
        if line.strip() == '/done':
            break
        lines.append(line)
    return '\n'.join(lines)


async def amain():
    server = CodeAgent()
    await server.initialize()  # Initialize the server first
    
    # Get prompt from user
    prompt = get_user_prompt()
    if not prompt.strip():
        print("Error: Empty prompt")
        return

    # Run the agent
    state = await server.run_prompt(prompt)

    # Print the conversation history
    print("\nConversation History:")
    print("=" * 80)
    for event in state.history:
        source = event.source.value
        if hasattr(event, "content"):
            content = event.content
            print(f"\n{source}:\n{content}")
    print("=" * 80)


def main():
    asyncio.run(amain())


if __name__ == "__main__":
    main() 