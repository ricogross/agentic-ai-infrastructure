"use client";

import { CopilotChat, useConfigureSuggestions } from "@copilotkit/react-core/v2";

// Static suggestions
function Suggestions() {
  useConfigureSuggestions({
    suggestions: [
      {
        title: "Show all data",
        message:
          "List every table in the database. Also show the content of each table.",
      },
      {
        title: "Read meeting notes",
        message:
          "What files are in the sandbox? Read the meeting notes for me.",
      },
      {
        title: "Top products by orders",
        message:
          "Which products have the most orders? Show me a ranking with the order counts.",
      },
    ],
    available: "always",
  });
  return null;
}

export default function HomePage() {
  return (
    <div className="h-full flex flex-col">
      <header className="shrink-0 px-6 py-4 border-b border-zinc-200 dark:border-zinc-700">
        <h1 className="text-xl font-semibold">Agentic AI Orchestrator</h1>
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          MCP + A2A + AG-UI &mdash; Ask about the database, files, or anything
          else.
        </p>
      </header>
      <div className="flex-1 min-h-0">
        <Suggestions />
        <CopilotChat />
      </div>
    </div>
  );
}
