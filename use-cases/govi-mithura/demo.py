"""Run Govi Mithura through the Agent Kernel CLI."""

from agentkernel.cli import CLI

from agent import register_module

register_module()

if __name__ == "__main__":
    CLI.main()
