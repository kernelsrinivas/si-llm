import { createFileRoute } from "@tanstack/react-router";
import { LlmApp } from "@/components/si/llm-app";

export const Route = createFileRoute("/")({ component: LlmApp });
