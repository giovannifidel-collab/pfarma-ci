import { readFile } from "node:fs/promises";

const prompt = await readFile(".github/photo-ai/preparatore-v2.prompt.md", "utf8");
const schema = JSON.parse(await readFile(".github/photo-ai/preparatore-v2.schema.json", "utf8"));

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const requiredPromptMarkers = [
  "MODELLO DECISIONALE ORBITALE",
  "PANNELLO MULTI-ESPERTO INTERNO",
  "V-TAPER E RIMODELLAMENTO VISIVO",
  "ricomposizione",
  "vita",
];
for (const marker of requiredPromptMarkers) {
  assert(prompt.toLowerCase().includes(marker.toLowerCase()), `Prompt marker missing: ${marker}`);
}

const analysis = schema?.properties?.analysis;
assert(analysis?.type === "object", "analysis schema missing");
const priorityAreaEnum = analysis?.properties?.priorities?.items?.properties?.area?.enum;
assert(Array.isArray(priorityAreaEnum), "strategic priority enum missing");
for (const area of ["v_taper", "waist_contrast", "shoulder_width", "lat_width", "upper_back", "upper_chest", "recomposition"]) {
  assert(priorityAreaEnum.includes(area), `Strategic area missing: ${area}`);
}

const exerciseEnum = schema?.properties?.plan?.properties?.days?.items?.properties?.exercises?.items?.properties?.exerciseId?.enum;
assert(Array.isArray(exerciseEnum) && exerciseEnum.length >= 20, "exercise catalog enum unexpectedly small");
for (const id of ["pike_pushup", "reverse_snow_angel", "plank", "fast_march"]) {
  assert(exerciseEnum.includes(id), `Smoke-safe exercise missing: ${id}`);
}

const smokeResult = {
  analysis: {
    analysisConfidence: "medium",
    imageQuality: { front: "usable", side: "usable", back: "usable" },
    priorities: [
      { area: "v_taper", observation: "Contrasto parte alta/vita migliorabile rispetto all'obiettivo estetico.", confidence: "medium", trainingImplication: "Aumentare frequenza di lavoro per spalle e dorsali senza promettere riduzione localizzata." },
      { area: "waist_contrast", observation: "La strategia deve combinare ricomposizione generale e proporzioni della parte alta.", confidence: "medium", trainingImplication: "Usare cardio sostenibile e core di controllo insieme a lavoro ipertrofico mirato." },
      { area: "recomposition", observation: "L'obiettivo visivo richiede miglioramento complessivo della composizione corporea.", confidence: "medium", trainingImplication: "Programmare densità e aderenza senza eccesso di volume non prioritario." }
    ],
    limitations: ["Smoke test tecnico: nessuna inferenza clinica o biometrica."],
    summary: "Smoke test Strategic Trainer: output goal-driven con V-taper, contrasto vita/parte alta e ricomposizione."
  },
  plan: {
    summary: "Scheda tecnica di prova non attivabile automaticamente.",
    rationale: [
      "Priorità estetiche ordinate per impatto sull'obiettivo.",
      "Ricomposizione reale distinta dal rimodellamento visivo.",
      "Vincoli e sicurezza prevalgono sulle priorità estetiche."
    ],
    safetyNote: "Output sintetico usato solo per validare il contratto dati senza chiamare Codex.",
    days: [
      {
        day: 1,
        title: "Smoke test upper body",
        durationMinutes: 25,
        emphasis: "Full body",
        warmupMinutes: 4,
        exercises: [
          { exerciseId: "pike_pushup", sets: 3, repsMin: 8, repsMax: 12, seconds: null, restSeconds: 60, reserveReps: 2 },
          { exerciseId: "reverse_snow_angel", sets: 3, repsMin: 10, repsMax: 15, seconds: null, restSeconds: 45, reserveReps: 2 },
          { exerciseId: "plank", sets: 3, repsMin: null, repsMax: null, seconds: 30, restSeconds: 30, reserveReps: null }
        ],
        finisher: null
      }
    ]
  }
};

assert(smokeResult.analysis.priorities.length >= 3 && smokeResult.analysis.priorities.length <= 8, "priority count invalid");
assert(smokeResult.plan.rationale.length >= 3, "rationale too short");
assert(smokeResult.plan.days[0].exercises.every((e) => exerciseEnum.includes(e.exerciseId)), "unknown exercise in smoke result");
assert(smokeResult.analysis.priorities.every((p) => priorityAreaEnum.includes(p.area)), "unknown strategic priority in smoke result");

console.log("PASS: Preparatore V2 Strategic Trainer smoke contract valid; Codex not invoked.");
