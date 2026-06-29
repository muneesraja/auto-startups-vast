"""No-op nodes for workflow termination."""
from google.adk.agents.context import Context
from google.adk.workflow import FunctionNode


async def pipeline_complete(ctx: Context) -> None:
    print("✅ [pipeline_complete] Nothing to do — all artifacts present.")


pipeline_complete_node = FunctionNode(func=pipeline_complete, name="pipeline_complete_node")
