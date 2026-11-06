import { createServerFn } from "@tanstack/react-start";

const BASE = "http://127.0.0.1:8765";

type Part = { ref: string; pkg: string; x: number; y: number };
type Net = { name: string; a: string; b: string };
type Track = { name: string; a: string; b: string; width: number; points: number[][] };
type Drc = { rule: string; status: string; detail: string };
type Cad = {
  length: number | null;
  width: number | null;
  thickness: number | null;
  hole: number;
  fillet: number;
};
export type Snapshot = {
  pcb: { parts: Part[]; nets: Net[]; tracks: Track[]; released: boolean };
  cad: Cad;
  drc: Drc[];
  mass: { cm3: number; grams: number } | null;
  work: {
    symbols: { ref: string; pkg: string }[];
    wires: { name: string; a: string; b: string }[];
    bom: { pkg: string; footprint: string; role: string; value: string; refs: string; qty: number }[];
    footprints: { ref: string; fp: string }[];
    sim: string;
    view3d: string;
    fab: string;
    assembly: string;
    stack: string;
    industry: string;
    board: string;
    chip: { name: string; status: string; detail: string }[];
    rules: { name: string; status: string; detail: string }[];
    coverage: { group: string; name: string; status: string; detail: string }[];
    outline: number[];
    datasheets: { ref: string; mpn: string; package: string; pins: number; pitch: number; body: string; land: string; nets: string }[];
    signal: string;
    desk: string;
    focus: string;
    ipcClass: string;
    cell: {
      name: string;
      note: string;
      width: number;
      height: number;
      devices: { name: string; type: string; w: number; l: number; g: string }[];
      shapes: { kind: string; x: number; y: number; w: number; h: number }[];
    } | null;
    ipc: { name: string; status: string; detail: string }[];
  };
};

export type McpLink = {
  id: string;
  title: string;
  ok: boolean;
  tools: string[];
  transport: string;
  target: string;
};
export type ToolCall = { server: string; tool: string; args: { key: string; value: string }[] };
export type AskBody = {
  ok: true;
  reply: string;
  commands: string[];
  runtime: string;
  op: string;
  state: Snapshot;
  heldout: number;
  params: number;
  needsApproval: boolean;
  proposalId: string;
  calls: ToolCall[];
};

export type RunMode = "auto" | "semi" | "man";

function modeOf(value: unknown): RunMode {
  return value === "auto" || value === "semi" ? value : "man";
}
function str(v: unknown, fallback = "") {
  return typeof v === "string" ? v : fallback;
}
function num(v: unknown, fallback = 0) {
  return typeof v === "number" && Number.isFinite(v) ? v : fallback;
}
function numOrNull(v: unknown) {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function cellOf(raw: unknown) {
  if (!raw || typeof raw !== "object") return null;
  const bag = raw as { name?: unknown; note?: unknown; width?: unknown; height?: unknown; devices?: unknown; shapes?: unknown };
  if (!str(bag.name)) return null;
  const devices = Array.isArray(bag.devices) ? bag.devices : [];
  const shapes = Array.isArray(bag.shapes) ? bag.shapes : [];
  return {
    name: str(bag.name),
    note: str(bag.note),
    width: num(bag.width),
    height: num(bag.height),
    devices: devices.map((row) => {
      const item = row as { name?: unknown; type?: unknown; w?: unknown; l?: unknown; g?: unknown };
      return { name: str(item.name), type: str(item.type), w: num(item.w), l: num(item.l), g: str(item.g) };
    }),
    shapes: shapes.map((row) => {
      const item = row as { kind?: unknown; x?: unknown; y?: unknown; w?: unknown; h?: unknown };
      return { kind: str(item.kind), x: num(item.x), y: num(item.y), w: num(item.w), h: num(item.h) };
    }),
  };
}

function linksOf(raw: unknown): McpLink[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((row) => {
      const bag = row as { id?: unknown; title?: unknown; ok?: unknown; tools?: unknown; transport?: unknown; target?: unknown };
      const tools = Array.isArray(bag.tools) ? bag.tools.map((item) => str(item)).filter(Boolean) : [];
      return {
        id: str(bag.id),
        title: str(bag.title, str(bag.id)),
        ok: Boolean(bag.ok),
        tools,
        transport: str(bag.transport),
        target: str(bag.target),
      };
    })
    .filter((row) => row.id);
}

function snapshotOf(raw: unknown): Snapshot {
  const bag = (raw ?? {}) as {
    pcb?: { parts?: unknown; nets?: unknown; released?: unknown };
    cad?: Record<string, unknown>;
    drc?: unknown;
    mass?: { cm3?: unknown; grams?: unknown } | null;
    work?: {
      symbols?: unknown;
      wires?: unknown;
      bom?: unknown;
      footprints?: unknown;
      sim?: unknown;
      view3d?: unknown;
      fab?: unknown;
      assembly?: unknown;
      stack?: unknown;
      industry?: unknown;
      board?: unknown;
      chip?: unknown;
      rules?: unknown;
      coverage?: unknown;
      outline?: unknown;
      datasheets?: unknown;
      signal?: unknown;
      desk?: unknown;
      focus?: unknown;
      ipc_class?: unknown;
      cell?: unknown;
      ipc?: unknown;
    };
  };
  const parts = Array.isArray(bag.pcb?.parts) ? bag.pcb.parts : [];
  const nets = Array.isArray(bag.pcb?.nets) ? bag.pcb.nets : [];
  const tracks = Array.isArray(bag.pcb?.tracks) ? bag.pcb.tracks : [];
  const drc = Array.isArray(bag.drc) ? bag.drc : [];
  return {
    pcb: {
      released: Boolean(bag.pcb?.released),
      parts: parts.map((p) => {
        const row = p as Part;
        return { ref: str(row.ref), pkg: str(row.pkg), x: num(row.x), y: num(row.y) };
      }),
      nets: nets.map((n) => {
        const row = n as Net;
        return { name: str(row.name), a: str(row.a), b: str(row.b) };
      }),
      tracks: tracks.map((row) => {
        const track = row as { name?: unknown; a?: unknown; b?: unknown; width?: unknown; points?: unknown };
        const points = Array.isArray(track.points) ? track.points : [];
        return {
          name: str(track.name),
          a: str(track.a),
          b: str(track.b),
          width: num(track.width),
          points: points.map((point) => {
            const pair = point as number[];
            return [num(pair?.[0]), num(pair?.[1])];
          }),
        };
      }),
    },
    cad: {
      length: numOrNull(bag.cad?.length),
      width: numOrNull(bag.cad?.width),
      thickness: numOrNull(bag.cad?.thickness),
      hole: num(bag.cad?.hole),
      fillet: num(bag.cad?.fillet),
    },
    drc: drc.map((d) => {
      const row = d as Drc;
      return { rule: str(row.rule), status: str(row.status), detail: str(row.detail) };
    }),
    mass:
      bag.mass && typeof bag.mass === "object"
        ? { cm3: num(bag.mass.cm3), grams: num(bag.mass.grams) }
        : null,
    work: {
      symbols: Array.isArray(bag.work?.symbols)
        ? bag.work.symbols.map((row) => {
            const item = row as { ref?: unknown; pkg?: unknown };
            return { ref: str(item.ref), pkg: str(item.pkg) };
          })
        : [],
      wires: Array.isArray(bag.work?.wires)
        ? bag.work.wires.map((row) => {
            const item = row as { name?: unknown; a?: unknown; b?: unknown };
            return { name: str(item.name), a: str(item.a), b: str(item.b) };
          })
        : [],
      bom: Array.isArray(bag.work?.bom)
        ? bag.work.bom.map((row) => {
            const item = row as { pkg?: unknown; footprint?: unknown; role?: unknown; value?: unknown; refs?: unknown; qty?: unknown };
            const refs = Array.isArray(item.refs) ? item.refs.map((ref) => str(ref)).filter(Boolean).join(", ") : str(item.refs);
            return { pkg: str(item.pkg), footprint: str(item.footprint), role: str(item.role), value: str(item.value), refs, qty: num(item.qty) };
          })
        : [],
      footprints: Array.isArray(bag.work?.footprints)
        ? bag.work.footprints.map((row) => {
            const item = row as { ref?: unknown; fp?: unknown };
            return { ref: str(item.ref), fp: str(item.fp) };
          })
        : [],
      sim: str(bag.work?.sim),
      view3d: str(bag.work?.view3d),
      fab: str(bag.work?.fab),
      assembly: str(bag.work?.assembly),
      stack: str(bag.work?.stack),
      industry: str(bag.work?.industry),
      board: str(bag.work?.board),
      chip: Array.isArray(bag.work?.chip)
        ? bag.work.chip.map((row) => {
            const item = row as { name?: unknown; status?: unknown; detail?: unknown };
            return { name: str(item.name), status: str(item.status), detail: str(item.detail) };
          })
        : [],
      rules: Array.isArray(bag.work?.rules)
        ? bag.work.rules.map((row) => {
            const item = row as { name?: unknown; status?: unknown; detail?: unknown };
            return { name: str(item.name), status: str(item.status), detail: str(item.detail) };
          })
        : [],
      coverage: Array.isArray(bag.work?.coverage)
        ? bag.work.coverage.map((row) => {
            const item = row as { group?: unknown; name?: unknown; status?: unknown; detail?: unknown };
            return { group: str(item.group), name: str(item.name), status: str(item.status), detail: str(item.detail) };
          })
        : [],
      outline: Array.isArray(bag.work?.outline) ? bag.work.outline.map((item) => num(item)).filter((item) => item > 0) : [],
      datasheets: Array.isArray(bag.work?.datasheets)
        ? bag.work.datasheets.map((row) => {
            const item = row as { ref?: unknown; mpn?: unknown; package?: unknown; pins?: unknown; pitch?: unknown; body?: unknown; land?: unknown; nets?: unknown };
            return {
              ref: str(item.ref),
              mpn: str(item.mpn),
              package: str(item.package),
              pins: num(item.pins),
              pitch: num(item.pitch),
              body: str(item.body),
              land: str(item.land),
              nets: str(item.nets),
            };
          })
        : [],
      signal: str(bag.work?.signal),
      desk: str(bag.work?.desk),
      focus: str(bag.work?.focus),
      ipcClass: str(bag.work?.ipc_class),
      cell: cellOf(bag.work?.cell),
      ipc: Array.isArray(bag.work?.ipc)
        ? bag.work.ipc.map((row) => {
            const item = row as { name?: unknown; status?: unknown; detail?: unknown };
            return { name: str(item.name), status: str(item.status), detail: str(item.detail) };
          })
        : [],
    },
  };
}

function callsOf(raw: unknown): ToolCall[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((row) => {
      const bag = row as { server?: unknown; tool?: unknown; args?: unknown };
      const args = Array.isArray(bag.args)
        ? bag.args
            .map((item) => {
              const arg = item as { key?: unknown; value?: unknown };
              return { key: str(arg.key), value: str(arg.value) };
            })
            .filter((arg) => arg.key)
        : [];
      return { server: str(bag.server), tool: str(bag.tool), args };
    })
    .filter((call) => call.tool);
}

function askOf(raw: unknown): AskBody {
  const bag = raw as {
    reply?: unknown;
    commands?: unknown;
    runtime?: unknown;
    op?: unknown;
    state?: unknown;
    model?: { heldout_exact?: unknown; params?: unknown };
    needsApproval?: unknown;
    proposalId?: unknown;
    calls?: unknown;
  };
  const commands = Array.isArray(bag.commands) ? bag.commands.map((item) => str(item)) : [];
  return {
    ok: true,
    reply: str(bag.reply),
    commands,
    runtime: str(bag.runtime),
    op: str(bag.op),
    state: snapshotOf(bag.state),
    heldout: num(bag.model?.heldout_exact),
    params: num(bag.model?.params),
    needsApproval: Boolean(bag.needsApproval),
    proposalId: str(bag.proposalId),
    calls: callsOf(bag.calls),
  };
}

async function readJson(path: string, body?: Record<string, unknown>) {
  const res = await fetch(BASE + path, {
    method: body ? "POST" : "GET",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(String(res.status));
  return (await res.json()) as unknown;
}

export const uploadDatasheet = createServerFn({ method: "POST" })
  .validator((input: unknown) => {
    const bag = (input ?? {}) as { name?: unknown; text?: unknown; pdf?: unknown };
    const text = str(bag.text).slice(0, 200_000);
    const pdf = str(bag.pdf).slice(0, 2_000_000);
    if (!text && !pdf) throw new Error("Missing datasheet");
    return { name: str(bag.name).slice(0, 120), text, pdf };
  })
  .handler(async ({ data }): Promise<AskBody | { ok: false; error: string }> => {
    try {
      const raw = await readJson("/datasheet", { text: data.text, pdf: data.pdf });
      return askOf(raw);
    } catch {
      return { ok: false, error: "The datasheet could not be read." };
    }
  });

export const askModel = createServerFn({ method: "POST" })
  .validator((input: unknown) => {
    if (!input || typeof input !== "object") throw new Error("Missing text");
    const text = String((input as { text?: unknown }).text ?? "").trim().slice(0, 500);
    if (!text) throw new Error("Missing text");
    return { text };
  })
  .handler(async ({ data }): Promise<AskBody | { ok: false; error: string }> => {
    try {
      const raw = await readJson("/ask", { text: data.text });
      return askOf(raw);
    } catch {
      return { ok: false, error: "The PyTorch model server is not running yet." };
    }
  });

export const modelHealth = createServerFn({ method: "GET" }).handler(
  async (): Promise<
    | { ok: true; heldout: number; params: number; tools: string[]; servers: McpLink[]; state: Snapshot; mode: RunMode }
    | { ok: false; error: string }
  > => {
    try {
      const health = (await readJson("/health")) as {
        model?: { heldout_exact?: unknown; params?: unknown };
        tools?: unknown;
        servers?: unknown;
        mode?: unknown;
      };
      const state = (await readJson("/state")) as { state?: unknown };
      const tools = Array.isArray(health.tools) ? health.tools.map((t) => str(t)).filter(Boolean) : [];
      return {
        ok: true,
        heldout: num(health.model?.heldout_exact),
        params: num(health.model?.params),
        tools,
        servers: linksOf(health.servers),
        state: snapshotOf(state.state),
        mode: modeOf(health.mode),
      };
    } catch {
      return { ok: false, error: "Model server offline" };
    }
  },
);

export const addMcp = createServerFn({ method: "POST" })
  .validator((input: unknown) => {
    const bag = (input ?? {}) as { preset?: unknown; name?: unknown; transport?: unknown; target?: unknown };
    const preset = str(bag.preset).slice(0, 16);
    const transport = str(bag.transport) === "stdio" ? "stdio" : "http";
    return {
      preset,
      name: str(bag.name).slice(0, 32),
      transport,
      target: str(bag.target).slice(0, 240),
    };
  })
  .handler(async ({ data }): Promise<{ ok: true; servers: McpLink[] } | { ok: false; error: string }> => {
    try {
      const payload = data.preset ? { preset: data.preset } : { name: data.name, transport: data.transport, target: data.target };
      const raw = (await readJson("/mcp/add", payload)) as { ok?: unknown; error?: unknown; server?: unknown; servers?: unknown };
      if (!raw.ok) return { ok: false, error: str(raw.error, "Could not connect.") };
      const listed = (await readJson("/health")) as { servers?: unknown };
      return { ok: true, servers: linksOf(listed.servers) };
    } catch {
      return { ok: false, error: "Could not connect." };
    }
  });

export const removeMcp = createServerFn({ method: "POST" })
  .validator((input: unknown) => {
    const bag = (input ?? {}) as { name?: unknown };
    const name = str(bag.name).slice(0, 32);
    if (!name) throw new Error("Missing name");
    return { name };
  })
  .handler(async ({ data }): Promise<{ ok: true; servers: McpLink[] } | { ok: false; error: string }> => {
    try {
      const raw = (await readJson("/mcp/remove", { name: data.name })) as { ok?: unknown; error?: unknown };
      if (!raw.ok) return { ok: false, error: str(raw.error, "Could not remove it.") };
      const listed = (await readJson("/health")) as { servers?: unknown };
      return { ok: true, servers: linksOf(listed.servers) };
    } catch {
      return { ok: false, error: "Could not remove it." };
    }
  });

export const setMode = createServerFn({ method: "POST" })
  .validator((input: unknown) => {
    const mode = str((input as { mode?: unknown } | null)?.mode);
    if (mode !== "auto" && mode !== "semi" && mode !== "man") throw new Error("Bad mode");
    return { mode };
  })
  .handler(async ({ data }): Promise<{ ok: true; mode: RunMode } | { ok: false; error: string }> => {
    try {
      const raw = (await readJson("/mode", { mode: data.mode })) as { ok?: unknown; mode?: unknown; error?: unknown };
      if (!raw.ok) return { ok: false, error: str(raw.error, "Could not set the mode.") };
      return { ok: true, mode: modeOf(raw.mode) };
    } catch {
      return { ok: false, error: "Could not set the mode." };
    }
  });

export const approveCall = createServerFn({ method: "POST" })
  .validator((input: unknown) => {
    const bag = (input ?? {}) as { proposalId?: unknown; decision?: unknown };
    const decision = str(bag.decision);
    if (decision !== "allow" && decision !== "always" && decision !== "deny") throw new Error("Bad decision");
    const proposalId = str(bag.proposalId).slice(0, 32);
    if (!proposalId) throw new Error("Missing approval");
    return { proposalId, decision };
  })
  .handler(async ({ data }): Promise<AskBody | { ok: false; error: string }> => {
    try {
      const raw = await readJson("/approve", { proposalId: data.proposalId, decision: data.decision });
      return askOf(raw);
    } catch {
      return { ok: false, error: "The approval did not go through." };
    }
  });
