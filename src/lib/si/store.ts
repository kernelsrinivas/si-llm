import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import {
  LIBRARY,
  SEED_ADAPTER,
  answer,
  applyLesson,
  buildPcb,
  lessonFromNote,
  type Adapter,
  type CadModel,
  type CamModel,
  type Domain,
  type PrintModel,
  type PcbModel,
  type SimKind,
  type Turn,
  type VisionRead,
} from "./model";

export type Desk = Domain | "train" | "analyze" | "brief";

type SiState = {
  desk: Desk;
  modality: Turn["modality"];
  adapter: Adapter;
  pcb: PcbModel;
  cad: CadModel;
  cam: CamModel;
  print: PrintModel;
  simKind: SimKind;
  turns: Turn[];
  learned: string[];
  vision: VisionRead | null;
  draft: string;
  setDesk: (desk: Desk) => void;
  setModality: (modality: Turn["modality"]) => void;
  setDraft: (draft: string) => void;
  setVision: (vision: VisionRead | null) => void;
  patchCad: (patch: Partial<CadModel>) => void;
  patchCam: (patch: Partial<CamModel>) => void;
  patchPrint: (patch: Partial<PrintModel>) => void;
  setSimKind: (simKind: SimKind) => void;
  setPcbStage: (stage: number) => void;
  loadBrief: (brief: string) => void;
  send: (modality?: Turn["modality"]) => string | null;
  rate: (id: string, stars: number) => void;
  learn: (id: string) => void;
  learnNote: (note: string) => void;
};

const pcb0 = buildPcb("usb-c sensor node", SEED_ADAPTER);

const cad0: CadModel = {
  name: "Mounting plate",
  length: 80,
  width: 40,
  thickness: 6,
  hole: 8,
  fillet: 3,
  material: "6061-T6",
};

const cam0: CamModel = {
  toolMm: 6,
  feed: 800,
  spindle: 12000,
  stepdown: 1,
  stock: "aluminum",
};

const print0: PrintModel = {
  material: "PLA",
  nozzle: 0.4,
  layer: 0.2,
  infill: 20,
  walls: 3,
  supports: false,
  bed: 220,
};

function uid() {
  return Math.random().toString(36).slice(2, 10);
}

export const useSi = create<SiState>()(
  persist(
    (set, get) => ({
      desk: "brief",
      modality: "text",
      adapter: SEED_ADAPTER,
      pcb: pcb0,
      cad: cad0,
      cam: cam0,
      print: print0,
      simKind: "thermal",
      turns: [
        {
          id: "welcome",
          role: "si",
          domain: "studio",
          modality: "text",
          at: 0,
          text: "SI-LLM is online. I run a full PCB flow, parametric CAD, CAM toolpaths, a print planner, and thermal, stress, and signal checks. Text, voice, or a photo. Lessons on Train change how the next design is released.",
        },
      ],
      learned: [],
      vision: null,
      draft: "",
      setDesk: (desk) => set({ desk }),
      setModality: (modality) => set({ modality }),
      setDraft: (draft) => set({ draft }),
      setVision: (vision) => set({ vision }),
      patchCad: (patch) => set({ cad: { ...get().cad, ...patch } }),
      patchCam: (patch) => set({ cam: { ...get().cam, ...patch } }),
      patchPrint: (patch) => set({ print: { ...get().print, ...patch } }),
      setSimKind: (simKind) => set({ simKind }),
      setPcbStage: (stage) => set({ pcb: { ...get().pcb, stage } }),
      loadBrief: (brief) => {
        const pcb = buildPcb(brief, get().adapter);
        set({ pcb: { ...pcb, stage: 0 }, desk: "pcb", draft: brief });
      },
      send: (modality) => {
        const s = get();
        const mode = modality ?? s.modality;
        const text = s.draft.trim() || (mode === "vision" && s.vision ? `Look at ${s.vision.name}` : "");
        if (!text) return null;
        const domainHint: Domain | "studio" =
          s.desk === "train" || s.desk === "analyze" || s.desk === "brief" ? "studio" : s.desk;
        const result = answer({
          text,
          domainHint,
          modality: mode,
          adapter: s.adapter,
          pcb: s.pcb,
          cad: s.cad,
          cam: s.cam,
          print: s.print,
          simKind: s.simKind,
          vision: s.vision,
        });
        const at = Date.now();
        const nextDesk: Desk = result.domain === "studio" ? s.desk : result.domain;
        set({
          draft: "",
          desk: nextDesk,
          pcb: result.pcb ? { ...result.pcb, stage: 0 } : s.pcb,
          turns: [
            ...s.turns,
            {
              id: uid(),
              role: "you" as const,
              text,
              domain: result.domain,
              modality: mode,
              at,
            },
            {
              id: uid(),
              role: "si" as const,
              text: result.text,
              domain: result.domain,
              modality: mode,
              at: at + 1,
            },
          ].slice(-48),
        });
        return result.text;
      },
      rate: (id, stars) =>
        set({
          turns: get().turns.map((t) => (t.id === id ? { ...t, stars } : t)),
        }),
      learn: (id) => {
        const lesson = LIBRARY.find((l) => l.id === id);
        if (!lesson || get().learned.includes(id)) return;
        set({
          adapter: applyLesson(get().adapter, lesson),
          learned: [...get().learned, id],
          print:
            lesson.apply.printMaterial != null
              ? { ...get().print, material: lesson.apply.printMaterial }
              : get().print,
        });
      },
      learnNote: (note) => {
        const lesson = lessonFromNote(note.trim());
        if (!lesson.note) return;
        set({
          adapter: applyLesson(get().adapter, lesson),
          learned: [...get().learned, lesson.id],
          print:
            lesson.apply.printMaterial != null
              ? { ...get().print, material: lesson.apply.printMaterial }
              : get().print,
        });
      },
    }),
    {
      name: "si-llm-v1",
      skipHydration: true,
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({
        desk: s.desk,
        modality: s.modality,
        adapter: s.adapter,
        pcb: s.pcb,
        cad: s.cad,
        cam: s.cam,
        print: s.print,
        simKind: s.simKind,
        turns: s.turns,
        learned: s.learned,
        vision: s.vision,
      }),
    },
  ),
);
