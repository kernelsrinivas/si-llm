import { createServerFn } from "@tanstack/react-start";

const SYSTEM = `You are SI-LLM, a hardware specialist covering PCB design (schematic, netlist, placement, routing, DRC, stackup, Gerber, BOM), mechanical CAD, CAM toolpaths and G-code, FDM/resin 3D printing, and thermal, stress, and signal simulation.
Use the local engine context. Be concrete: dimensions, units, pass/fail. No preamble, no markdown headings. At most 160 words. If the context is insufficient, say what measurement is missing.`;

export const deepen = createServerFn({ method: "POST" })
  .validator((input: unknown) => {
    if (!input || typeof input !== "object") throw new Error("Missing prompt");
    const bag = input as { prompt?: unknown; context?: unknown };
    const prompt = String(bag.prompt ?? "").trim().slice(0, 1600);
    const context = String(bag.context ?? "").trim().slice(0, 2400);
    if (!prompt) throw new Error("Missing prompt");
    return { prompt, context };
  })
  .handler(async ({ data }) => {
    const apiKey = process.env.XAI_API_KEY;
    if (!apiKey) {
      return {
        ok: false as const,
        error: "Core model is offline here. The local specialist still runs every desk.",
      };
    }
    try {
      const res = await fetch("https://api.x.ai/v1/chat/completions", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${apiKey}`,
        },
        body: JSON.stringify({
          model: "grok-4.5",
          max_tokens: 380,
          temperature: 0.3,
          messages: [
            { role: "system", content: SYSTEM },
            {
              role: "user",
              content: `Local engine context:\n${data.context}\n\nEngineer asked:\n${data.prompt}`,
            },
          ],
        }),
      });
      if (!res.ok) {
        return { ok: false as const, error: `Core model returned ${res.status}. Local answer still stands.` };
      }
      const body = (await res.json()) as {
        choices?: { message?: { content?: string } }[];
      };
      const text = body.choices?.[0]?.message?.content?.trim() ?? "";
      if (!text) return { ok: false as const, error: "Core model returned an empty note." };
      return { ok: true as const, text };
    } catch {
      return { ok: false as const, error: "Core model could not be reached. Local answer still stands." };
    }
  });
