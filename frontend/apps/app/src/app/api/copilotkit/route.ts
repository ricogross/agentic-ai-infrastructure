import {
  CopilotRuntime,
  ExperimentalEmptyAdapter,
  copilotRuntimeNextJSAppRouterEndpoint,
} from "@copilotkit/runtime";
import { LangGraphAgent } from "@copilotkit/runtime/langgraph";
import { NextRequest } from "next/server";

// Connect to the LangGraph orchestrator server
const defaultAgent = new LangGraphAgent({
  deploymentUrl:
    process.env.LANGGRAPH_DEPLOYMENT_URL || "http://localhost:8123",
  graphId: "orchestrator",
  langsmithApiKey: process.env.LANGSMITH_API_KEY || "",
});

// Wire up the CopilotKit Runtime as a Next.js POST handler
export const POST = async (req: NextRequest) => {
  const { handleRequest } = copilotRuntimeNextJSAppRouterEndpoint({
    endpoint: "/api/copilotkit",
    serviceAdapter: new ExperimentalEmptyAdapter(),
    runtime: new CopilotRuntime({
      agents: {
        default: defaultAgent,
      },
    }),
  });

  return handleRequest(req);
};
