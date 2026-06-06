<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

type Gauges = {
  evidence: number;
  durability: number;
  containment: number;
  verification: number;
};

type Phase = {
  id: string;
  index: string;
  label: string;
  title: string;
  failure: string;
  move: string;
  takeaway: string;
  // which schematic parts are illuminated
  on: string[];
  // which is the "hot" one this phase
  focus: string;
  // teletype lines for the telemetry feed
  feed: { t: string; kind: "user" | "model" | "tool" | "obs" | "mem" | "safe" | "crit" | "rt" | "eval"; text: string }[];
  gauges: Gauges;
  // optional inline note for the schematic
  note?: string;
};

const phases: Phase[] = [
  {
    id: "model",
    index: "01",
    label: "Bare Model",
    title: "Prompt in, text out. No way to inspect reality.",
    failure:
      "A single model call can explain ideas, but it cannot read files, run commands, or check tests. For real code work it is guessing.",
    move:
      "Start with the smallest useful system: a task, a model, an answer. Notice what it cannot do before adding anything.",
    takeaway: "If the answer must be proven, a bare model is not enough.",
    on: ["task", "model", "answer", "wire-task-model", "wire-model-answer"],
    focus: "model",
    feed: [
      { t: "00:00", kind: "user", text: "why is test_users.py failing on main?" },
      { t: "00:01", kind: "model", text: "likely a fixture or import issue (unverified)" },
      { t: "00:02", kind: "model", text: "answer returned (no observations gathered)" },
    ],
    gauges: { evidence: 5, durability: 0, containment: 0, verification: 0 },
    note: "no loop · no tools · no trace",
  },
  {
    id: "react",
    index: "02",
    label: "ReAct Loop",
    title: "Reason, act, observe, repeat. The trace becomes the unit of diagnosis.",
    failure:
      "Without a loop, the model commits to its first guess. Coding work needs to take a step, look, and try again.",
    move:
      "Wrap the model: pick an action, run it, append the observation, decide whether to continue or stop.",
    takeaway: "The trace, not the single response, becomes the artifact you read.",
    on: ["task", "model", "answer", "loop", "wire-task-model", "wire-model-answer"],
    focus: "loop",
    feed: [
      { t: "00:03", kind: "model", text: "step 1 · plan: inspect failing test" },
      { t: "00:04", kind: "model", text: "step 2 · pick action: read tests/test_users.py" },
      { t: "00:05", kind: "obs", text: "no action available · loop is empty" },
      { t: "00:06", kind: "model", text: "step 3 · need a tool surface" },
    ],
    gauges: { evidence: 15, durability: 0, containment: 0, verification: 0 },
    note: "loop running · no tools wired yet",
  },
  {
    id: "tools",
    index: "03",
    label: "Tools",
    title: "Tools turn guesses into checked observations.",
    failure:
      "A loop without tools is a hamster wheel. The model needs shell, files, search, and tests so each step can touch reality.",
    move:
      "Expose a small tool surface first. Add retrieval or MCP only when the trace shows the model is starved for evidence.",
    takeaway:
      "Tool design is part of the prompt surface. Fewer, legible, tested tools beat a pile of plugins.",
    on: [
      "task",
      "model",
      "answer",
      "loop",
      "tools",
      "wire-task-model",
      "wire-model-answer",
      "wire-model-tools",
    ],
    focus: "tools",
    feed: [
      { t: "00:07", kind: "tool", text: "shell · rg \"FAIL\" tests/" },
      { t: "00:08", kind: "obs", text: "tests/test_users.py::test_email_lowercase FAILED" },
      { t: "00:09", kind: "tool", text: "fs · read tests/test_users.py" },
      { t: "00:10", kind: "obs", text: "fixture seeded uppercase, code lowercases input" },
      { t: "00:11", kind: "tool", text: "shell · pytest tests/test_users.py -x" },
    ],
    gauges: { evidence: 55, durability: 5, containment: 0, verification: 10 },
    note: "shell · files · search · tests",
  },
  {
    id: "memory",
    index: "04",
    label: "Memory",
    title: "Durable context stops the agent from re-discovering the same facts.",
    failure:
      "Every turn starts cold. Repo conventions, prior decisions, and trace summaries get re-derived from scratch and burn tokens.",
    move:
      "Curate stable knowledge: AGENTS.md, progress notes, trace summaries, condenser policy. Make memory inspectable.",
    takeaway: "Memory is only useful when it is curated. Dump-everything memory is noise.",
    on: [
      "task",
      "model",
      "answer",
      "loop",
      "tools",
      "memory",
      "wire-task-model",
      "wire-model-answer",
      "wire-model-tools",
      "wire-model-memory",
    ],
    focus: "memory",
    feed: [
      { t: "00:12", kind: "mem", text: "load · AGENTS.md · python 3.11, pytest, ruff" },
      { t: "00:13", kind: "mem", text: "load · prior trace · email normalization touched 2x" },
      { t: "00:14", kind: "model", text: "skip env setup · already documented" },
      { t: "00:15", kind: "mem", text: "save · finding: fixture/casing mismatch" },
    ],
    gauges: { evidence: 60, durability: 60, containment: 0, verification: 10 },
    note: "AGENTS.md · notes · condenser",
  },
  {
    id: "safety",
    index: "05",
    label: "Safety",
    title: "Boundaries before autonomy. The harness decides what runs automatically.",
    failure:
      "The same tools that make the agent useful can delete files, leak secrets, or burn budget. Safety cannot live only in a prompt.",
    move:
      "Workspace isolation, permission gates, command policy, budget limits, human approval for risky actions.",
    takeaway: "Blast radius is a design choice, not a vibe.",
    on: [
      "task",
      "model",
      "answer",
      "loop",
      "tools",
      "memory",
      "safety",
      "wire-task-model",
      "wire-model-answer",
      "wire-model-tools",
      "wire-model-memory",
    ],
    focus: "safety",
    feed: [
      { t: "00:16", kind: "safe", text: "policy · sandbox=workspace · network=off" },
      { t: "00:17", kind: "safe", text: "deny · rm -rf · requires approval" },
      { t: "00:18", kind: "safe", text: "budget · 40k tokens · 90s wall" },
      { t: "00:19", kind: "tool", text: "shell · pytest -k test_email -x   [allowed]" },
    ],
    gauges: { evidence: 60, durability: 60, containment: 70, verification: 10 },
    note: "sandbox · policy · approvals · budget",
  },
  {
    id: "critic",
    index: "06",
    label: "Critic",
    title: "Verification keeps 'looks done' from becoming the finish line.",
    failure:
      "Agents stop too early or grade their own work generously. Confidence is not evidence.",
    move:
      "Tests, rubrics, external review, trace checks, and result tables decide whether the change is kept.",
    takeaway: "The course loop: predict, run, inspect, measure, keep.",
    on: [
      "task",
      "model",
      "answer",
      "loop",
      "tools",
      "memory",
      "safety",
      "critic",
      "wire-task-model",
      "wire-model-answer",
      "wire-model-tools",
      "wire-model-memory",
      "wire-model-critic",
    ],
    focus: "critic",
    feed: [
      { t: "00:20", kind: "model", text: "proposed patch · lowercase fixture seed" },
      { t: "00:21", kind: "crit", text: "rubric · regression · run full users suite" },
      { t: "00:22", kind: "tool", text: "shell · pytest tests/ -q" },
      { t: "00:23", kind: "obs", text: "47 passed · 0 failed" },
      { t: "00:24", kind: "crit", text: "verdict · keep · trace logged" },
    ],
    gauges: { evidence: 75, durability: 60, containment: 70, verification: 80 },
    note: "tests · rubrics · trace checks",
  },
  {
    id: "routing",
    index: "07",
    label: "Routing",
    title: "The harness picks the model. It does not call one model forever.",
    failure:
      "Easy tasks should not pay for the strongest model. Hard tasks need a recovery path when the cheap path stalls.",
    move:
      "Route by task shape. Escalate on evidence. Keep a benchmark table that compares cost per solved task.",
    takeaway: "Model choice becomes a policy you can defend with traces, not a habit.",
    on: [
      "task",
      "router",
      "model",
      "answer",
      "loop",
      "tools",
      "memory",
      "safety",
      "critic",
      "wire-router-model",
      "wire-task-router",
      "wire-model-answer",
      "wire-model-tools",
      "wire-model-memory",
      "wire-model-critic",
    ],
    focus: "router",
    feed: [
      { t: "00:25", kind: "rt", text: "classify · task=bugfix · size=S" },
      { t: "00:26", kind: "rt", text: "select · haiku-4-5 · attempt 1" },
      { t: "00:27", kind: "obs", text: "stalled · 2 loops, no new evidence" },
      { t: "00:28", kind: "rt", text: "escalate · sonnet-4-6 · context carried" },
      { t: "00:29", kind: "obs", text: "patch verified · log $/solved" },
    ],
    gauges: { evidence: 80, durability: 70, containment: 70, verification: 85 },
    note: "classify · escalate · log $/solved",
  },
  {
    id: "evidence",
    index: "08",
    label: "Benchmark",
    title: "A leaderboard row is an agent system, not a model score.",
    failure:
      "It is tempting to read a benchmark as a model ranking. Submissions are agent plus model: loop, tools, sandbox, verifier, stopping rule.",
    move:
      "Use Terminal-Bench as evidence that the full harness matters. Label every score with the agent that produced it.",
    takeaway: "Say 'agent + model'. Do not overclaim that the model alone earned the score.",
    on: [
      "task",
      "router",
      "model",
      "answer",
      "loop",
      "tools",
      "memory",
      "safety",
      "critic",
      "benchmark",
      "wire-router-model",
      "wire-task-router",
      "wire-model-answer",
      "wire-model-tools",
      "wire-model-memory",
      "wire-model-critic",
    ],
    focus: "benchmark",
    feed: [
      { t: "00:30", kind: "eval", text: "terminal-bench · task: real terminal env" },
      { t: "00:31", kind: "eval", text: "harness runs commands in a sandbox" },
      { t: "00:32", kind: "eval", text: "verifier inspects final filesystem state" },
      { t: "00:33", kind: "eval", text: "row recorded as agent + model" },
    ],
    gauges: { evidence: 90, durability: 80, containment: 85, verification: 95 },
    note: "agent + model · not model alone",
  },
];

const activeIndex = ref(0);
const stepEls = ref<HTMLElement[]>([]);
let observer: IntersectionObserver | null = null;
let reduceMotion = false;

const activePhase = computed(() => phases[activeIndex.value] ?? phases[0]);
const progressPct = computed(
  () => ((activeIndex.value + 1) / phases.length) * 100,
);

// gauges are tweened by CSS via custom property; we just bind the target values
const gaugeStyle = computed(() => ({
  "--g-evidence": `${activePhase.value.gauges.evidence}%`,
  "--g-durability": `${activePhase.value.gauges.durability}%`,
  "--g-containment": `${activePhase.value.gauges.containment}%`,
  "--g-verification": `${activePhase.value.gauges.verification}%`,
}));

function setStepEl(el: Element | null, index: number) {
  if (el instanceof HTMLElement) {
    stepEls.value[index] = el;
  }
}

function partClass(id: string) {
  return {
    on: activePhase.value.on.includes(id),
    focus: activePhase.value.focus === id,
  };
}

function kindColor(kind: string) {
  return `feed-${kind}`;
}

// staggered re-entry animation for feed lines when phase changes
const feedKey = ref(0);
watch(activeIndex, () => {
  feedKey.value += 1;
});

onMounted(() => {
  if (typeof window !== "undefined") {
    reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }
  observer = new IntersectionObserver(
    (entries) => {
      const hit = entries
        .filter((e) => e.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      const next = hit?.target.getAttribute("data-phase-index");
      if (next != null) {
        activeIndex.value = Number(next);
      }
    },
    {
      root: null,
      rootMargin: "-38% 0px -48% 0px",
      threshold: [0.15, 0.35, 0.6],
    },
  );
  stepEls.value.forEach((el) => observer?.observe(el));
});

onBeforeUnmount(() => observer?.disconnect());
</script>

<template>
  <section class="afc" aria-label="Visual intro scrollytelling console">
    <header class="afc-intro">
      <p class="afc-kicker">Scroll The Harness Into View</p>
      <h2>One task. Eight versions of the agent around the same model.</h2>
      <p>
        Each scroll step adds one harness component because a real failure mode
        appears. Watch the console: the schematic grows, the telemetry tape
        types new lines, and the gauges fill. The point is controlled design
        based on trace evidence, not more machinery.
      </p>
    </header>

    <div class="afc-layout">
      <!-- STICKY CONSOLE -->
      <div class="afc-stage" aria-live="polite">
        <div class="console" :data-phase="activePhase.id">
          <!-- Top status bar -->
          <div class="console-bar">
            <div class="bar-left">
              <span class="dot" />
              <span class="bar-title">HARNESS CONSOLE</span>
            </div>
            <div class="bar-task" :title="'task'">
              TASK · why is test_users.py failing on main?
            </div>
            <div class="bar-right">
              <span class="phase-num">{{ activePhase.index }}</span>
              <span class="phase-divider">/</span>
              <span class="phase-total">08</span>
            </div>
          </div>

          <!-- Completeness meter -->
          <div class="progress">
            <div class="progress-fill" :style="{ width: progressPct + '%' }" />
            <div class="progress-ticks">
              <span v-for="(p, i) in phases" :key="p.id" :class="{ on: i <= activeIndex }" />
            </div>
          </div>

          <!-- Main display: schematic + feed side by side -->
          <div class="console-main">
            <!-- LEFT: SVG schematic -->
            <div class="schematic">
              <div class="schematic-label">
                <span>SCHEMATIC</span>
                <strong>{{ activePhase.label }}</strong>
              </div>

              <svg viewBox="0 0 520 360" class="schematic-svg" role="img" aria-label="Agent system schematic">
                <!-- subtle grid -->
                <defs>
                  <pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse">
                    <path d="M 20 0 L 0 0 0 20" fill="none" stroke="rgb(249 240 217 / 7%)" stroke-width="1" />
                  </pattern>
                  <radialGradient id="halo" cx="50%" cy="50%" r="50%">
                    <stop offset="0%" stop-color="#ffff8b" stop-opacity="0.45" />
                    <stop offset="100%" stop-color="#ffff8b" stop-opacity="0" />
                  </radialGradient>
                  <linearGradient id="loopGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" stop-color="#ffff8b" stop-opacity="0.0" />
                    <stop offset="50%" stop-color="#ffff8b" stop-opacity="1" />
                    <stop offset="100%" stop-color="#ffff8b" stop-opacity="0.0" />
                  </linearGradient>
                </defs>
                <rect x="0" y="0" width="520" height="360" fill="url(#grid)" />

                <!-- crosshair -->
                <line x1="260" y1="0" x2="260" y2="360" stroke="rgb(249 240 217 / 10%)" stroke-dasharray="2 4" />
                <line x1="0" y1="180" x2="520" y2="180" stroke="rgb(249 240 217 / 10%)" stroke-dasharray="2 4" />

                <!-- wires (drawn behind nodes) -->
                <g class="wires">
                  <path id="w-task-model" class="wire" :class="partClass('wire-task-model')"
                    d="M 92 180 H 218" />
                  <path id="w-model-answer" class="wire" :class="partClass('wire-model-answer')"
                    d="M 302 180 H 428" />
                  <path id="w-task-router" class="wire" :class="partClass('wire-task-router')"
                    d="M 70 162 V 60 H 230" />
                  <path id="w-router-model" class="wire" :class="partClass('wire-router-model')"
                    d="M 260 90 V 150" />
                  <path id="w-model-memory" class="wire" :class="partClass('wire-model-memory')"
                    d="M 240 156 L 150 84" />
                  <path id="w-model-critic" class="wire" :class="partClass('wire-model-critic')"
                    d="M 282 156 L 380 84" />
                  <path id="w-model-tools" class="wire" :class="partClass('wire-model-tools')"
                    d="M 260 210 V 256" />
                </g>

                <!-- ReAct loop ring around the model -->
                <g class="loop-ring" :class="partClass('loop')">
                  <circle cx="260" cy="180" r="56" fill="none" stroke="#ffff8b" stroke-opacity="0.35" stroke-dasharray="3 6" />
                  <circle cx="260" cy="180" r="56" fill="none" stroke="url(#loopGrad)" stroke-width="2" class="loop-arc" />
                  <text x="260" y="120" class="loop-tag" text-anchor="middle">reason</text>
                  <text x="324" y="186" class="loop-tag" text-anchor="start">act</text>
                  <text x="260" y="248" class="loop-tag" text-anchor="middle">observe</text>
                </g>

                <!-- nodes -->
                <!-- Task -->
                <g class="node" :class="partClass('task')" transform="translate(12,150)">
                  <rect width="80" height="60" rx="6" />
                  <text x="40" y="24" text-anchor="middle" class="n-lbl">TASK</text>
                  <text x="40" y="44" text-anchor="middle" class="n-sub">prompt</text>
                </g>

                <!-- Router -->
                <g class="node" :class="partClass('router')" transform="translate(210,30)">
                  <rect width="100" height="60" rx="6" />
                  <text x="50" y="24" text-anchor="middle" class="n-lbl">ROUTER</text>
                  <text x="50" y="44" text-anchor="middle" class="n-sub">choose model</text>
                </g>

                <!-- Memory -->
                <g class="node" :class="partClass('memory')" transform="translate(80,30)">
                  <rect width="100" height="60" rx="6" />
                  <text x="50" y="24" text-anchor="middle" class="n-lbl">MEMORY</text>
                  <text x="50" y="44" text-anchor="middle" class="n-sub">artifacts</text>
                </g>

                <!-- Critic -->
                <g class="node" :class="partClass('critic')" transform="translate(340,30)">
                  <rect width="100" height="60" rx="6" />
                  <text x="50" y="24" text-anchor="middle" class="n-lbl">CRITIC</text>
                  <text x="50" y="44" text-anchor="middle" class="n-sub">verify</text>
                </g>

                <!-- Model (center, larger) -->
                <g class="node node-primary" :class="partClass('model')" transform="translate(218,150)">
                  <circle cx="0" cy="0" r="48" class="halo" fill="url(#halo)" />
                  <rect width="84" height="60" rx="8" />
                  <text x="42" y="24" text-anchor="middle" class="n-lbl">MODEL</text>
                  <text x="42" y="44" text-anchor="middle" class="n-sub">reason</text>
                </g>

                <!-- Answer -->
                <g class="node" :class="partClass('answer')" transform="translate(428,150)">
                  <rect width="80" height="60" rx="6" />
                  <text x="40" y="24" text-anchor="middle" class="n-lbl">RESULT</text>
                  <text x="40" y="44" text-anchor="middle" class="n-sub">answer / diff</text>
                </g>

                <!-- Tools cluster -->
                <g class="node tools-group" :class="partClass('tools')" transform="translate(180,256)">
                  <rect width="160" height="64" rx="6" />
                  <text x="80" y="20" text-anchor="middle" class="n-lbl">TOOLS</text>
                  <g class="tool-chips">
                    <rect x="10" y="32" width="40" height="22" rx="3" />
                    <text x="30" y="47" text-anchor="middle" class="n-chip">shell</text>
                    <rect x="60" y="32" width="40" height="22" rx="3" />
                    <text x="80" y="47" text-anchor="middle" class="n-chip">files</text>
                    <rect x="110" y="32" width="40" height="22" rx="3" />
                    <text x="130" y="47" text-anchor="middle" class="n-chip">test</text>
                  </g>
                </g>

                <!-- Safety containment ring around tools -->
                <g class="safety-ring" :class="partClass('safety')" transform="translate(160,238)">
                  <rect width="200" height="104" rx="14" fill="none" />
                  <text x="100" y="-2" text-anchor="middle" class="n-lbl-ring">SAFETY · sandbox · policy · budget</text>
                </g>
              </svg>

              <p class="schematic-note">{{ activePhase.note }}</p>
            </div>

            <!-- RIGHT: telemetry feed -->
            <div class="feed">
              <div class="feed-head">
                <span class="rec-dot" />
                <span class="feed-title">TELEMETRY · live trace</span>
              </div>
              <ol class="feed-list" :key="feedKey">
                <li
                  v-for="(line, i) in activePhase.feed"
                  :key="line.t + i"
                  :class="kindColor(line.kind)"
                  :style="{ animationDelay: i * 70 + 'ms' }"
                >
                  <span class="ts">{{ line.t }}</span>
                  <span class="kind">{{ line.kind }}</span>
                  <span class="msg">{{ line.text }}</span>
                </li>
              </ol>

              <!-- Benchmark readout appears in phase 08 -->
              <transition name="fade-up">
                <div v-if="activePhase.id === 'evidence'" class="bench">
                  <div class="bench-head">
                    <span>TERMINAL-BENCH · evidence card</span>
                    <strong>agent + model</strong>
                  </div>
                  <table class="bench-table">
                    <thead>
                      <tr>
                        <th>Agent</th>
                        <th>Model</th>
                        <th>Score</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td>OpenHands</td>
                        <td>Claude Opus 4.5</td>
                        <td>51.9%</td>
                      </tr>
                      <tr>
                        <td>Codex CLI</td>
                        <td>GPT-5</td>
                        <td>49.6%</td>
                      </tr>
                      <tr>
                        <td>OpenHands</td>
                        <td>GPT-5</td>
                        <td>43.8%</td>
                      </tr>
                    </tbody>
                  </table>
                  <p class="bench-foot">
                    Illustrative rows phrased from the public leaderboard
                    (captured June 2026). Every row is an <strong>agent system</strong>,
                    not a model in isolation. Swap the harness and the row moves.
                  </p>
                </div>
              </transition>
            </div>
          </div>

          <!-- Gauges -->
          <div class="gauges" :style="gaugeStyle">
            <div class="gauge">
              <div class="g-head"><span>EVIDENCE</span><strong>{{ activePhase.gauges.evidence }}</strong></div>
              <div class="g-bar"><div class="g-fill" data-key="evidence" /></div>
            </div>
            <div class="gauge">
              <div class="g-head"><span>DURABILITY</span><strong>{{ activePhase.gauges.durability }}</strong></div>
              <div class="g-bar"><div class="g-fill" data-key="durability" /></div>
            </div>
            <div class="gauge">
              <div class="g-head"><span>CONTAINMENT</span><strong>{{ activePhase.gauges.containment }}</strong></div>
              <div class="g-bar"><div class="g-fill" data-key="containment" /></div>
            </div>
            <div class="gauge">
              <div class="g-head"><span>VERIFICATION</span><strong>{{ activePhase.gauges.verification }}</strong></div>
              <div class="g-bar"><div class="g-fill" data-key="verification" /></div>
            </div>
          </div>
        </div>
      </div>

      <!-- SCROLLING NARRATIVE -->
      <div class="afc-steps">
        <article
          v-for="(phase, i) in phases"
          :key="phase.id"
          :ref="(el) => setStepEl(el as Element | null, i)"
          class="afc-step"
          :class="{ active: activeIndex === i }"
          :data-phase-index="i"
        >
          <div class="step-head">
            <span class="step-num">{{ phase.index }}</span>
            <span class="step-tag">{{ phase.label }}</span>
          </div>
          <h3>{{ phase.title }}</h3>
          <dl>
            <div>
              <dt>Failure mode</dt>
              <dd>{{ phase.failure }}</dd>
            </div>
            <div>
              <dt>Harness move</dt>
              <dd>{{ phase.move }}</dd>
            </div>
            <div>
              <dt>Keep</dt>
              <dd>{{ phase.takeaway }}</dd>
            </div>
          </dl>
        </article>
      </div>
    </div>

    <footer class="afc-sources">
      <p>
        Sources:
        <a href="https://research.google/blog/react-synergizing-reasoning-and-acting-in-language-models/" target="_blank" rel="noreferrer">ReAct</a>,
        <a href="https://www.anthropic.com/engineering/building-effective-agents" target="_blank" rel="noreferrer">Anthropic agent patterns</a>,
        <a href="https://openai.com/index/harness-engineering/" target="_blank" rel="noreferrer">OpenAI harness engineering</a>,
        <a href="https://docs.openhands.dev/sdk/arch/agent-server" target="_blank" rel="noreferrer">OpenHands Agent Server</a>,
        <a href="https://www.tbench.ai/" target="_blank" rel="noreferrer">Terminal-Bench</a>.
      </p>
    </footer>
  </section>
</template>

<style scoped>
.afc {
  width: 100%;
  margin: 48px 0;
}

/* ───── intro ───── */
.afc-intro {
  max-width: 780px;
  margin-bottom: 28px;
}
.afc-kicker {
  margin: 0;
  color: var(--oh-brown);
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.afc-intro h2 {
  margin: 8px 0 14px;
  color: var(--vp-c-text-1);
  font-family: "Quincy CF", var(--vp-font-family-base);
  font-size: clamp(34px, 5vw, 60px);
  font-weight: 400;
  line-height: 1.02;
}
.afc-intro p:last-child {
  margin: 0;
  color: var(--vp-c-text-2);
  font-size: 18px;
  line-height: 1.55;
}

/* ───── layout ───── */
.afc-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.25fr) minmax(320px, 0.85fr);
  gap: 28px;
  align-items: start;
}

.afc-stage {
  position: sticky;
  top: 92px;
}

/* ───── console panel ───── */
.console {
  position: relative;
  border: 1px solid #22150d;
  border-radius: 10px;
  background: #181009;
  background-image:
    radial-gradient(circle at 12% 0%, rgb(255 255 139 / 8%), transparent 40%),
    radial-gradient(circle at 88% 100%, rgb(227 23 0 / 7%), transparent 38%);
  box-shadow:
    0 22px 60px rgb(34 21 13 / 30%),
    inset 0 0 0 1px rgb(249 240 217 / 4%);
  color: #f9f0d9;
  overflow: hidden;
}

.console-bar {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 16px;
  align-items: center;
  padding: 11px 16px;
  border-bottom: 1px solid rgb(249 240 217 / 12%);
  background: linear-gradient(180deg, rgb(255 255 139 / 6%), transparent);
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.bar-left {
  display: flex;
  gap: 8px;
  align-items: center;
}
.bar-left .dot {
  display: inline-block;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #ff5942;
  box-shadow: 0 0 10px rgb(255 89 66 / 70%);
  animation: rec-pulse 1.6s ease-in-out infinite;
}
.bar-title {
  color: #f9f0d9;
  font-weight: 500;
}
.bar-task {
  color: rgb(249 240 217 / 70%);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bar-right {
  display: flex;
  gap: 4px;
  align-items: baseline;
  color: #ffff8b;
}
.phase-num {
  font-size: 16px;
  font-weight: 500;
}
.phase-divider,
.phase-total {
  color: rgb(249 240 217 / 50%);
}

@keyframes rec-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* progress bar */
.progress {
  position: relative;
  height: 4px;
  background: rgb(249 240 217 / 8%);
}
.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #ffff8b, #ffd400);
  transition: width 380ms cubic-bezier(0.22, 0.65, 0.3, 1);
}
.progress-ticks {
  position: absolute;
  inset: 0;
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  pointer-events: none;
}
.progress-ticks span {
  border-right: 1px solid rgb(24 16 9 / 70%);
}
.progress-ticks span:last-child {
  border-right: 0;
}

/* main */
.console-main {
  display: grid;
  grid-template-columns: 1.15fr 0.85fr;
  min-height: 410px;
}

/* ───── schematic ───── */
.schematic {
  position: relative;
  padding: 18px 18px 8px;
  border-right: 1px solid rgb(249 240 217 / 10%);
  background:
    linear-gradient(rgb(249 240 217 / 3%) 1px, transparent 1px) 0 0 / 22px 22px,
    linear-gradient(90deg, rgb(249 240 217 / 3%) 1px, transparent 1px) 0 0 / 22px 22px,
    radial-gradient(circle at 50% 55%, #221710, #100a06);
}
.schematic-label {
  display: flex;
  gap: 10px;
  align-items: baseline;
  margin-bottom: 8px;
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.schematic-label span { color: rgb(249 240 217 / 55%); }
.schematic-label strong { color: #ffff8b; font-weight: 500; }

.schematic-svg {
  display: block;
  width: 100%;
  height: auto;
  max-height: 340px;
}

.schematic-note {
  margin: 6px 0 0;
  color: rgb(249 240 217 / 50%);
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  letter-spacing: 0.04em;
  text-align: center;
  text-transform: uppercase;
}

/* SVG node styling */
:deep(.node) rect,
.node rect {
  fill: rgb(249 240 217 / 4%);
  stroke: rgb(249 240 217 / 22%);
  stroke-width: 1;
  transition: fill 320ms ease, stroke 320ms ease, opacity 320ms ease;
}
.node text {
  font-family: var(--vp-font-family-mono);
  font-size: 10px;
  letter-spacing: 0.04em;
  fill: rgb(249 240 217 / 40%);
  text-transform: uppercase;
  transition: fill 320ms ease;
}
.node .n-lbl {
  font-size: 11px;
  fill: rgb(249 240 217 / 55%);
  font-weight: 500;
}
.node .n-sub {
  font-size: 9.5px;
  letter-spacing: 0.05em;
}
.node .n-chip {
  font-size: 9px;
  fill: rgb(249 240 217 / 55%);
}
.node {
  opacity: 0.28;
  transition: opacity 320ms ease, transform 320ms ease;
}
.node.on {
  opacity: 1;
}
.node.on rect {
  fill: rgb(255 255 139 / 8%);
  stroke: rgb(255 255 139 / 55%);
}
.node.on text {
  fill: #f9f0d9;
}
.node.on .n-lbl {
  fill: #ffff8b;
}
.node.focus rect {
  fill: rgb(255 255 139 / 18%);
  stroke: #ffff8b;
}
.node.focus {
  transform: translateY(-1px);
}
.node-primary.on rect {
  fill: rgb(255 255 139 / 14%);
  stroke: #ffff8b;
}
.node-primary .halo {
  opacity: 0;
  transition: opacity 320ms ease;
}
.node-primary.on .halo {
  opacity: 0.9;
}

/* tools chips */
.tools-group .tool-chips rect {
  fill: rgb(255 255 139 / 6%);
  stroke: rgb(255 255 139 / 30%);
}
.tools-group.on .tool-chips rect {
  fill: rgb(255 255 139 / 14%);
  stroke: #ffff8b;
}

/* safety ring */
.safety-ring rect {
  stroke-dasharray: 5 6;
  stroke: rgb(227 23 0 / 0%);
  transition: stroke 320ms ease;
}
.safety-ring .n-lbl-ring {
  font-family: var(--vp-font-family-mono);
  font-size: 9.5px;
  letter-spacing: 0.08em;
  fill: rgb(255 92 70 / 0%);
  text-transform: uppercase;
  transition: fill 320ms ease;
}
.safety-ring.on rect {
  stroke: rgb(255 92 70 / 75%);
}
.safety-ring.on .n-lbl-ring {
  fill: rgb(255 121 96 / 95%);
}

/* wires */
.wire {
  fill: none;
  stroke: rgb(249 240 217 / 12%);
  stroke-width: 1.4;
  stroke-dasharray: 4 5;
  transition: stroke 320ms ease, stroke-opacity 320ms ease;
}
.wire.on {
  stroke: #ffff8b;
  stroke-opacity: 0.7;
  animation: wire-flow 1.6s linear infinite;
}
@keyframes wire-flow {
  to {
    stroke-dashoffset: -18;
  }
}

/* loop */
.loop-ring {
  opacity: 0;
  transition: opacity 320ms ease;
}
.loop-ring.on {
  opacity: 1;
}
.loop-ring .loop-tag {
  font-family: var(--vp-font-family-mono);
  font-size: 9px;
  letter-spacing: 0.08em;
  fill: rgb(255 255 139 / 75%);
  text-transform: uppercase;
}
.loop-arc {
  transform-box: fill-box;
  transform-origin: center;
  animation: loop-spin 3.6s linear infinite;
}
@keyframes loop-spin {
  to {
    transform: rotate(360deg);
  }
}

/* ───── telemetry feed ───── */
.feed {
  display: flex;
  flex-direction: column;
  padding: 14px 16px 16px;
  background:
    repeating-linear-gradient(
      to bottom,
      rgb(249 240 217 / 2%) 0 1px,
      transparent 1px 4px
    ),
    #120c08;
}
.feed-head {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 10px;
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.rec-dot {
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #ffff8b;
  box-shadow: 0 0 8px rgb(255 255 139 / 80%);
}
.feed-title {
  color: rgb(249 240 217 / 70%);
}

.feed-list {
  display: grid;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.feed-list li {
  display: grid;
  gap: 8px;
  grid-template-columns: 44px 38px 1fr;
  align-items: baseline;
  padding: 6px 8px;
  border: 1px solid rgb(249 240 217 / 8%);
  border-left: 2px solid rgb(255 255 139 / 35%);
  border-radius: 4px;
  background: rgb(249 240 217 / 3%);
  color: #f9f0d9;
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
  line-height: 1.35;
  opacity: 0;
  animation: feed-in 320ms ease forwards;
}
.feed-list li .ts {
  color: rgb(249 240 217 / 45%);
}
.feed-list li .kind {
  color: rgb(255 255 139 / 80%);
  font-weight: 500;
  text-transform: lowercase;
}
.feed-list li .msg {
  color: rgb(249 240 217 / 90%);
  word-break: break-word;
}
@keyframes feed-in {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* kind-specific accents */
.feed-user { border-left-color: rgb(255 255 139 / 70%) !important; }
.feed-model { border-left-color: rgb(122 199 255 / 80%) !important; }
.feed-model .kind { color: #92cbff; }
.feed-tool { border-left-color: rgb(95 207 153 / 80%) !important; }
.feed-tool .kind { color: #6cd9a3; }
.feed-obs { border-left-color: rgb(178 178 178 / 70%) !important; }
.feed-obs .kind { color: #cfc8b7; }
.feed-mem { border-left-color: rgb(160 226 122 / 80%) !important; }
.feed-mem .kind { color: #a5e07d; }
.feed-safe { border-left-color: rgb(255 121 96 / 90%) !important; }
.feed-safe .kind { color: #ff8e76; }
.feed-crit { border-left-color: rgb(255 195 120 / 90%) !important; }
.feed-crit .kind { color: #ffc378; }
.feed-rt { border-left-color: rgb(214 156 255 / 85%) !important; }
.feed-rt .kind { color: #d49cff; }
.feed-eval { border-left-color: #ffff8b !important; background: rgb(255 255 139 / 6%); }
.feed-eval .kind { color: #ffff8b; }

/* benchmark card */
.bench {
  margin-top: 14px;
  border: 1px solid rgb(255 255 139 / 45%);
  border-radius: 6px;
  background: rgb(255 255 139 / 6%);
  padding: 12px;
}
.bench-head {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  color: #ffff8b;
  font-family: var(--vp-font-family-mono);
  font-size: 10.5px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.bench-head strong {
  color: #f9f0d9;
  font-weight: 500;
}
.bench-table {
  width: 100%;
  border-collapse: collapse;
  color: #f9f0d9;
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
}
.bench-table th,
.bench-table td {
  padding: 6px 4px;
  border-bottom: 1px solid rgb(249 240 217 / 10%);
  text-align: left;
}
.bench-table th {
  color: rgb(249 240 217 / 55%);
  font-weight: 400;
}
.bench-table td:last-child {
  color: #ffff8b;
  font-weight: 500;
  text-align: right;
}
.bench-foot {
  margin: 10px 0 0;
  color: rgb(249 240 217 / 55%);
  font-size: 11px;
  line-height: 1.4;
}
.bench-foot strong {
  color: #ffff8b;
  font-weight: 500;
}

.fade-up-enter-active {
  transition: opacity 280ms ease, transform 280ms ease;
}
.fade-up-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

/* ───── gauges ───── */
.gauges {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0;
  border-top: 1px solid rgb(249 240 217 / 10%);
  background: linear-gradient(180deg, rgb(249 240 217 / 3%), transparent);
}
.gauge {
  padding: 12px 14px;
  border-right: 1px solid rgb(249 240 217 / 8%);
}
.gauge:last-child {
  border-right: 0;
}
.g-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 8px;
  color: rgb(249 240 217 / 70%);
  font-family: var(--vp-font-family-mono);
  font-size: 10.5px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.g-head strong {
  color: #ffff8b;
  font-family: var(--vp-font-family-mono);
  font-size: 14px;
  font-weight: 500;
}
.g-bar {
  position: relative;
  height: 5px;
  border-radius: 999px;
  background: rgb(249 240 217 / 8%);
  overflow: hidden;
}
.g-fill {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #ffff8b, #ffd400);
  transition: width 460ms cubic-bezier(0.22, 0.65, 0.3, 1);
  width: 0;
}
.g-fill[data-key="evidence"] { width: var(--g-evidence, 0%); }
.g-fill[data-key="durability"] { width: var(--g-durability, 0%); }
.g-fill[data-key="containment"] {
  width: var(--g-containment, 0%);
  background: linear-gradient(90deg, #ff8e76, #ffb169);
}
.g-fill[data-key="verification"] {
  width: var(--g-verification, 0%);
  background: linear-gradient(90deg, #a5e07d, #ffe165);
}

/* ───── steps ───── */
.afc-steps {
  display: grid;
  gap: 20px;
}
.afc-step {
  min-height: 440px;
  border: 1px solid rgb(34 21 13 / 14%);
  border-radius: 10px;
  background: rgb(255 255 255 / 32%);
  padding: 22px 22px 24px;
  transition: border-color 200ms ease, background-color 200ms ease, box-shadow 200ms ease;
}
.afc-step.active {
  border-color: #22150d;
  background: #fffceb;
  box-shadow: 0 18px 38px rgb(34 21 13 / 10%);
}
.step-head {
  display: flex;
  gap: 10px;
  align-items: baseline;
  margin-bottom: 6px;
}
.step-num {
  color: #22150d;
  font-family: var(--vp-font-family-mono);
  font-size: 13px;
  letter-spacing: 0.04em;
  background: #ffff8b;
  border: 1px solid #22150d;
  border-radius: 4px;
  padding: 1px 7px;
}
.step-tag {
  color: var(--oh-brown);
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.afc-step h3 {
  margin: 6px 0 18px;
  color: var(--vp-c-text-1);
  font-family: "Quincy CF", var(--vp-font-family-base);
  font-size: 28px;
  font-weight: 400;
  line-height: 1.1;
}
.afc-step dl,
.afc-step dl > div {
  display: grid;
  gap: 12px;
  margin: 0;
}
.afc-step dt {
  color: #22150d;
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.afc-step dd {
  margin: 0;
  color: var(--vp-c-text-2);
  font-size: 16px;
  line-height: 1.55;
}

/* ───── sources ───── */
.afc-sources {
  margin-top: 24px;
  color: var(--vp-c-text-2);
  font-size: 13px;
}
.afc-sources a {
  color: var(--vp-c-text-1);
  text-decoration: underline;
  text-underline-offset: 3px;
}

/* ───── dark mode tweaks ───── */
:global(.dark) .afc-step {
  background: rgb(241 234 224 / 4%);
  border-color: rgb(249 240 217 / 14%);
}
:global(.dark) .afc-step.active {
  background: rgb(255 225 101 / 8%);
  border-color: #ffe165;
  box-shadow: 0 18px 38px rgb(0 0 0 / 40%);
}
:global(.dark) .step-num {
  background: #ffe165;
  color: #22150d;
  border-color: #ffe165;
}
:global(.dark) .afc-step h3 {
  color: #f9f0d9;
}
:global(.dark) .afc-step dt {
  color: #ffe165;
}

/* ───── responsive ───── */
@media (max-width: 1080px) {
  .afc-layout {
    grid-template-columns: 1fr;
  }
  .afc-stage {
    position: relative;
    top: auto;
  }
  .console-main {
    grid-template-columns: 1fr;
  }
  .schematic {
    border-right: 0;
    border-bottom: 1px solid rgb(249 240 217 / 10%);
  }
}

@media (max-width: 720px) {
  .afc {
    margin: 28px 0;
  }
  .afc-intro h2 { font-size: 32px; }
  .afc-intro p:last-child { font-size: 15px; }
  .console-bar {
    grid-template-columns: 1fr auto;
    gap: 8px;
  }
  .bar-task {
    display: none;
  }
  .gauges {
    grid-template-columns: repeat(2, 1fr);
  }
  .gauge:nth-child(2n) {
    border-right: 0;
  }
  .gauge:nth-child(-n+2) {
    border-bottom: 1px solid rgb(249 240 217 / 8%);
  }
  .afc-step {
    min-height: 0;
    padding: 18px;
  }
  .afc-step h3 { font-size: 22px; }
  .feed-list li {
    grid-template-columns: 40px 32px 1fr;
    font-size: 10.5px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .wire.on,
  .loop-arc,
  .bar-left .dot {
    animation: none !important;
  }
  .feed-list li {
    animation: none !important;
    opacity: 1;
  }
  .progress-fill,
  .g-fill,
  .node,
  .wire {
    transition: none !important;
  }
}
</style>
