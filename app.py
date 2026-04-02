"""
STEM Education Chatbot — Multi-Kit Support
Flask backend with LLM-powered Q&A (OpenRouter), guardrails, and image support.
Supports: Karaoke Speaker Kit, School Electronics Experiment Kit.
"""

import os
import json
import re
import urllib.request
import urllib.error
from flask import Flask, request, jsonify, render_template

app = Flask(__name__, static_folder="static", template_folder="templates")

# ─── Load .env file ──────────────────────────────────────────────────────────
ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(ENV_PATH):
    with open(ENV_PATH, "r") as ef:
        for line in ef:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

# ─── OpenRouter LLM Model ────────────────────────────────────────────────────
LLM_MODEL = "google/gemini-2.0-flash-lite-001"

# ─── Load all experiment kits ─────────────────────────────────────────────────
BASE_DIR = os.path.dirname(__file__)

KIT_FILES = {
    "karaoke": os.path.join(BASE_DIR, "knowledge_base.json"),
    "school_kit": os.path.join(BASE_DIR, "knowledge_base_school_kit.json"),
}

DEFAULT_KIT = "karaoke"

# Per-kit scope keywords for guardrail detection
KIT_SCOPE_KEYWORDS = {
    "karaoke": [
        "speaker", "karaoke", "bluetooth", "pcb", "circuit", "board", "wire",
        "battery", "panel", "screw", "switch", "knob", "potentiometer", "volume",
        "microphone", "mic", "usb", "type-c", "type c", "charging", "port",
        "assembly", "step", "build", "connect", "install", "insert", "attach",
        "place", "secure", "fix", "mount", "solder", "cable", "tie",
        "sound", "audio", "signal", "frequency", "vibration", "resonance",
        "current", "voltage", "resistance", "ohm", "capacitor", "inductor",
        "ncert", "science", "physics", "experiment", "stem", "learn",
        "explain", "concept",
        "sub step", "substep", "detail", "more", "help", "show", "image",
        "next", "previous", "first", "last", "start", "finish", "complete",
        "component", "part", "piece", "tool", "safety", "tip", "warning",
        "working", "not working", "problem", "issue", "trouble", "stuck",
        "hello", "hi", "hey", "thanks", "thank", "bye", "ok", "okay",
        "list", "all steps", "overview", "summary", "progress",
        "electromagnetic", "induction", "energy", "power", "watt",
        "connector", "slot", "groove", "tab", "hole", "cutout",
        "wood", "wooden", "enclosure", "box", "body", "frame",
        "cone", "magnet", "coil", "driver", "amplifier",
        "analog", "digital", "radio", "wave", "hz", "ghz",
        "lithium", "rechargeable", "charge", "discharge",
        "polarity", "positive", "negative", "red", "black",
    ],
    "school_kit": [
        "circuit", "led", "battery", "wire", "switch", "resistor", "transistor",
        "motor", "fan", "propeller", "solar", "panel", "potentiometer", "speed",
        "series", "parallel", "conductor", "insulator", "electrolysis",
        "touch sensor", "alarm", "buzzer", "piezo", "doorbell", "door bell",
        "torch", "flashlight", "traffic light", "rain alarm", "tornado", "vortex",
        "windmill", "optical illusion", "energy bridge", "home supply",
        "aluminium", "aluminum", "diy", "foam", "push pin", "ring connector",
        "pencil", "graphite", "salt water", "9v", "aa battery",
        "current", "voltage", "resistance", "ohm", "polarity",
        "positive", "negative", "red", "black", "collector", "base", "emitter",
        "ncert", "science", "physics", "experiment", "stem", "learn",
        "explain", "concept", "step", "build", "connect", "experiment",
        "sub step", "substep", "detail", "more", "help", "show",
        "next", "previous", "first", "last", "start", "finish", "complete",
        "component", "part", "piece", "tool", "safety", "tip", "warning",
        "working", "not working", "problem", "issue", "trouble", "stuck",
        "hello", "hi", "hey", "thanks", "thank", "bye", "ok", "okay",
        "list", "all steps", "overview", "summary", "progress",
        "energy", "power", "watt", "dc motor", "renewable",
        "charge", "discharge", "short circuit",
    ],
}

# Per-kit experiment terms for question matching
KIT_EXPERIMENT_TERMS = {
    "karaoke": [
        "speaker", "karaoke", "build", "assemble", "step", "wire",
        "board", "battery", "panel", "screw", "switch", "mic",
        "volume", "knob", "port", "charge", "bluetooth", "connect",
        "circuit", "sound", "this", "experiment",
        "kit", "project", "next", "previous", "potentiometer", "pcb",
        "enclosure", "wooden", "wood", "driver", "cone", "magnet",
        "amplifier", "frequency", "vibration", "current", "voltage",
        "resistance", "polarity", "lithium", "rechargeable", "watt",
    ],
    "school_kit": [
        "circuit", "led", "battery", "wire", "switch", "resistor",
        "transistor", "motor", "fan", "propeller", "solar", "panel",
        "potentiometer", "speed", "series", "parallel", "conductor",
        "insulator", "electrolysis", "touch", "sensor", "alarm",
        "buzzer", "piezo", "doorbell", "torch", "traffic", "rain",
        "tornado", "windmill", "illusion", "energy", "bridge",
        "aluminium", "diy", "foam", "pencil", "graphite",
        "this", "experiment", "kit", "project", "next", "previous",
        "step", "build", "connect", "circuit", "current", "voltage",
        "resistance", "watt",
    ],
}

# Per-kit strong terms for final scope check
KIT_STRONG_TERMS = {
    "karaoke": [
        "speaker", "karaoke", "bluetooth", "pcb", "circuit", "battery",
        "panel", "screw", "switch", "mic", "microphone", "volume", "knob",
        "potentiometer", "wire", "solder", "connector", "assembly", "step",
        "experiment", "kit", "build", "ncert", "stem",
    ],
    "school_kit": [
        "circuit", "led", "battery", "resistor", "transistor", "motor",
        "fan", "solar", "switch", "potentiometer", "wire", "conductor",
        "insulator", "electrolysis", "sensor", "alarm", "buzzer", "torch",
        "doorbell", "traffic", "tornado", "windmill", "experiment", "kit",
        "build", "ncert", "stem", "step",
    ],
}

KITS = {}


def _build_keyword_index(steps):
    """Build keyword index for a set of steps."""
    keyword_index = {}
    for step in steps:
        for kw in step["keywords"]:
            keyword_index[kw.lower()] = step["step_number"]
        keyword_index[step["title"].lower()] = step["step_number"]
        keyword_index[step["topic"].lower()] = step["step_number"]
        keyword_index[f"step {step['step_number']}"] = step["step_number"]
        keyword_index[f"step{step['step_number']}"] = step["step_number"]
        keyword_index[f"experiment {step['step_number']}"] = step["step_number"]
        keyword_index[f"exp {step['step_number']}"] = step["step_number"]
    return keyword_index


def _build_system_prompt(kb):
    """Build a dynamic system prompt from a knowledge base."""
    name = kb["experiment"]
    description = kb["description"]
    components = ", ".join(kb["components"][:15])
    ncert = "\n".join(f"- {c}" for c in kb["ncert_connections"])
    num_steps = len(kb["steps"])
    step_type = "experiment" if num_steps > 15 else "assembly step"

    return f"""You are a friendly STEM education assistant for the "{name}" experiment kit.
{description}

YOUR SCOPE — answer ALL of these:
- {step_type.title()}s, sub-steps, troubleshooting for the {num_steps}-step kit
- ANY science concept related to how the kit works: electricity, magnetism, circuits, signals, waves, frequency, resonance, vibration, energy conversion, electromagnetic induction, Ohm's law, voltage, current, resistance, capacitors, inductors, LEDs, motors, solar energy, etc.
- ANY physics/NCERT topic that connects to the experiments
- General STEM/electronics/physics questions that a student might ask while doing these experiments
- Components, tools, safety tips for the kit

ONLY REJECT questions that are completely unrelated to science, electronics, or this experiment kit — such as politics, movies, celebrities, sports scores, recipes, coding homework, etc.
When rejecting, say: "That's outside what I can help with! I'm here for the {name} — ask me about experiment steps, science concepts, or troubleshooting!"

IMPORTANT: When in doubt, ANSWER the question and connect it back to the experiments. Students are curious — encourage their scientific thinking!

RULES:
1. Keep answers concise, student-friendly, and encouraging.
2. Use **bold** for important terms and step numbers.
3. When explaining science concepts, reference NCERT chapters where applicable.
4. If the user asks for sub-steps or more detail, break the step into smaller numbered actions.
5. Always connect science explanations back to the experiment kit when possible.
6. Always be encouraging — this is a learning experience for young students.

EXPERIMENT OVERVIEW:
- {num_steps} {step_type}s in the kit
- Components: {components}
- NCERT connections:
{ncert}"""


def _build_guardrail_response(kb):
    """Build a kit-specific guardrail response."""
    name = kb["experiment"]
    num_steps = len(kb["steps"])
    return {
        "text": (
            f"I appreciate your curiosity! However, I'm specifically designed to help you with the **{name}**. "
            f"I can assist you with:\n\n"
            f"• 🔧 **Experiment steps** — detailed instructions for each of the {num_steps} experiments\n"
            f"• 📋 **Sub-steps** — breaking down any step into smaller, easier actions\n"
            f"• 🔬 **Science concepts** — the NCERT-related physics & electronics behind each step\n"
            f"• ⚠️ **Safety tips** — precautions for each experiment\n"
            f"• 🧰 **Components & tools** — what you need\n\n"
            f"Please ask me something about the experiments, and I'll be happy to help! 😊"
        ),
        "images": [],
        "is_guardrail": True
    }


def load_kit(kit_id, kb_path):
    """Load a single kit from its knowledge base JSON file."""
    with open(kb_path, "r", encoding="utf-8") as f:
        kb = json.load(f)
    KITS[kit_id] = {
        "kb": kb,
        "steps": kb["steps"],
        "experiment_name": kb["experiment"],
        "components": kb["components"],
        "ncert_connections": kb["ncert_connections"],
        "learning_objectives": kb["learning_objectives"],
        "keyword_index": _build_keyword_index(kb["steps"]),
        "system_prompt": _build_system_prompt(kb),
        "guardrail_response": _build_guardrail_response(kb),
    }


# Load all kits at startup
for kit_id, kb_path in KIT_FILES.items():
    if os.path.exists(kb_path):
        load_kit(kit_id, kb_path)
        print(f"✅ Loaded kit: {kit_id} ({KITS[kit_id]['experiment_name']}, {len(KITS[kit_id]['steps'])} steps)")

# Backward-compat aliases for default kit
STEPS = KITS[DEFAULT_KIT]["steps"]
EXPERIMENT_NAME = KITS[DEFAULT_KIT]["experiment_name"]
COMPONENTS = KITS[DEFAULT_KIT]["components"]
NCERT_CONNECTIONS = KITS[DEFAULT_KIT]["ncert_connections"]
LEARNING_OBJECTIVES = KITS[DEFAULT_KIT]["learning_objectives"]


def _get_kit(kit_id=None):
    """Safely get a kit by ID, falling back to default."""
    if kit_id and kit_id in KITS:
        return KITS[kit_id]
    return KITS[DEFAULT_KIT]


def _word_match(keyword: str, text: str) -> bool:
    """Match keyword in text using word boundaries for short words."""
    if len(keyword) <= 3:
        return bool(re.search(r'\b' + re.escape(keyword) + r'\b', text))
    return keyword in text


def is_in_scope(message: str, kit_id: str = None) -> bool:
    """Check if user message is within the experiment/STEM scope."""
    msg_lower = message.lower().strip()
    scope_keywords = KIT_SCOPE_KEYWORDS.get(kit_id or DEFAULT_KIT, KIT_SCOPE_KEYWORDS[DEFAULT_KIT])
    experiment_terms = KIT_EXPERIMENT_TERMS.get(kit_id or DEFAULT_KIT, KIT_EXPERIMENT_TERMS[DEFAULT_KIT])
    strong_terms = KIT_STRONG_TERMS.get(kit_id or DEFAULT_KIT, KIT_STRONG_TERMS[DEFAULT_KIT])

    # Greetings are always in scope
    greetings = ["hi", "hello", "hey", "thanks", "thank you", "bye", "ok", "okay", "help", "start"]
    if msg_lower in greetings:
        return True

    # Check for step/experiment references
    if re.search(r"(step|exp|experiment)\s*\d+", msg_lower):
        return True

    # Check for scope keywords
    for kw in scope_keywords:
        if _word_match(kw, msg_lower):
            return True

    # Check for question patterns about the experiment
    question_patterns = [
        r"how (do|to|does|can|should)",
        r"what (is|are|does|do|should)",
        r"why (is|are|do|does|should)",
        r"where (is|are|do|does|should)",
        r"which (step|part|component|wire|panel|experiment)",
        r"can (i|you|we)",
        r"tell me",
        r"show me",
        r"explain",
    ]
    for pattern in question_patterns:
        if re.search(pattern, msg_lower):
            for term in experiment_terms:
                if _word_match(term, msg_lower):
                    return True

    # Final check: does the message contain at least one strong experiment term?
    for term in strong_terms:
        if _word_match(term, msg_lower):
            return True

    return False


def find_relevant_steps(message: str, kit_id: str = None) -> list:
    """Find steps relevant to the user's message using keyword matching."""
    kit = _get_kit(kit_id)
    steps = kit["steps"]
    keyword_index = kit["keyword_index"]
    msg_lower = message.lower().strip()
    matched_steps = {}

    # Direct step/experiment number reference
    step_nums = re.findall(r"(?:step|exp|experiment)\s*(\d+)", msg_lower)
    for num_str in step_nums:
        num = int(num_str)
        if 1 <= num <= len(steps):
            matched_steps[num] = 100  # Highest priority

    # Keyword matching with scoring
    for kw, step_num in keyword_index.items():
        if kw in msg_lower:
            score = len(kw) * 2  # Longer keyword matches score higher
            if step_num in matched_steps:
                matched_steps[step_num] = max(matched_steps[step_num], score)
            else:
                matched_steps[step_num] = score

    # Word-level matching for partial hits
    words = re.findall(r'\b\w+\b', msg_lower)
    for step in steps:
        step_text = f"{step['title']} {step['topic']} {' '.join(step['keywords'])}".lower()
        for word in words:
            if len(word) > 3 and word in step_text:
                sn = step["step_number"]
                matched_steps[sn] = matched_steps.get(sn, 0) + 1

    # Sort by score descending
    sorted_steps = sorted(matched_steps.items(), key=lambda x: x[1], reverse=True)
    return [steps[sn - 1] for sn, _ in sorted_steps[:3]]


# ─── Query Classification ────────────────────────────────────────────────────

def classify_query(message: str) -> str:
    """Classify whether the user is asking a concept/theory question or a step/instruction question.
    Returns 'concept', 'step', or 'general'.
    """
    msg_lower = message.lower().strip()

    # Concept patterns — asking about why/what/how something works (theory)
    concept_patterns = [
        r"what is (a |an |the )?(concept|science|physics|theory|principle)",
        r"what is (a |an |the )?(potentiometer|electromagnetic|inductor|capacitor|resistor|ohm|frequency|resonance|vibration|impedance|amplif|diaphragm|baffle|bluetooth|pcb|circuit)",
        r"how does (a |an |the )?(speaker|potentiometer|bluetooth|battery|circuit|switch|microphone|amplifier|capacitor|inductor|resistor|driver|magnet|coil|sound|pcb) work",
        r"why (do|does|is|are|should) (we|i|the|a|this)",
        r"what (happens|would happen) (if|when)",
        r"explain (the )?(concept|science|physics|working|principle|theory|role|purpose|function)",
        r"(what|explain) .*(concept|theory|principle|physics|science|ncert)",
        r"what (is|are) .*(used for|purpose|function|role)",
        r"(tell|teach) me (about|more about) .*(concept|science|physics|theory|ncert|working|principle)",
        r"science (behind|of|concept)",
        r"ncert",
        r"which class|which chapter",
    ]

    # Step/instruction patterns — asking how to do something (action)
    step_patterns = [
        r"how (do|to|can|should) (i|we) (do|perform|complete|start|assemble|build|connect|attach|install|place|insert|mount|secure|fix)",
        r"(show|give|tell) me (the )?(sub.?steps|steps|instructions|procedure|process)",
        r"step\s*\d+",
        r"(what|which) (step|steps)",
        r"(how to|how do i) (connect|attach|install|place|insert|mount|secure|fix|wire|screw|build|assemble)",
        r"(next step|previous step|go back|what's next|after this|before this)",
        r"(start|begin) (from|with|at)",
        r"(sub.?steps|detailed steps|break.?down)",
        r"what (should|do) i do (next|now|first|after|before)",
        r"(safety|tool|tools) (tip|tips|needed|required)",
    ]

    concept_score = sum(1 for p in concept_patterns if re.search(p, msg_lower))
    step_score = sum(1 for p in step_patterns if re.search(p, msg_lower))

    if concept_score > step_score:
        return "concept"
    if step_score > concept_score:
        return "step"
    if concept_score > 0:
        return "concept"
    return "general"


def format_step_response(step: dict, detail_level: str = "normal") -> dict:
    """Format a step into a chat response."""
    response = {
        "step_number": step["step_number"],
        "title": step["title"],
        "topic": step["topic"],
        "image_url": step["image_url"],
    }

    if detail_level == "brief":
        response["text"] = f"**Step {step['step_number']}: {step['title']}**\n\n{step['detailed_instructions']}"
    elif detail_level == "substeps":
        substeps_text = "\n".join([f"  {i+1}. {s}" for i, s in enumerate(step["sub_steps"])])
        response["text"] = (
            f"**Step {step['step_number']}: {step['title']}** — Detailed Sub-steps\n\n"
            f"{step['detailed_instructions']}\n\n"
            f"**Sub-steps:**\n{substeps_text}"
        )
    elif detail_level == "concept":
        response["text"] = (
            f"**Step {step['step_number']}: {step['title']}** — Science Concept\n\n"
            f"🔬 {step['science_concept']}"
        )
    elif detail_level == "safety":
        tips = "\n".join([f"  ⚠️ {t}" for t in step["safety_tips"]])
        tools = ", ".join(step["tools_needed"])
        response["text"] = (
            f"**Step {step['step_number']}: {step['title']}** — Safety & Tools\n\n"
            f"**Safety Tips:**\n{tips}\n\n"
            f"**Tools Needed:** {tools}"
        )
    else:  # normal / full
        substeps_text = "\n".join([f"  {i+1}. {s}" for i, s in enumerate(step["sub_steps"])])
        tips = "\n".join([f"  ⚠️ {t}" for t in step["safety_tips"]])
        tools = ", ".join(step["tools_needed"])
        response["text"] = (
            f"**Step {step['step_number']}: {step['title']}**\n"
            f"*Topic: {step['topic']}*\n\n"
            f"{step['detailed_instructions']}\n\n"
            f"**Sub-steps:**\n{substeps_text}\n\n"
            f"🔬 **Science Concept:** {step['science_concept']}\n\n"
            f"**Safety Tips:**\n{tips}\n\n"
            f"**Tools Needed:** {tools}"
        )

    return response



def llm_scope_check(message: str, kit_id: str = None) -> bool:
    """Use LLM to check if a query is related to the active experiment kit.
    Returns True if relevant, False if off-topic. Falls back to False on errors."""
    if not OPENROUTER_API_KEY or OPENROUTER_API_KEY == "your-openrouter-api-key-here":
        return False

    kit = _get_kit(kit_id)
    kb = kit["kb"]
    name = kit["experiment_name"]
    components = ", ".join(kb["components"][:10])

    prompt = (
        f"You are a scope classifier for a STEM education chatbot about the \"{name}\" experiment kit.\n"
        f"The kit involves: {kb['description'][:200]}\n"
        f"Components include: {components}\n\n"
        "Relevant topics include: assembly/experiment steps, electronic components, circuits, wires, batteries, "
        "science concepts (electricity, magnetism, sound, energy, Ohm's law), "
        "NCERT physics, STEM education, troubleshooting, safety tips, and tools.\n\n"
        "Is the following user question related to this experiment kit or its topics?\n"
        f"User question: \"{message}\"\n\n"
        "Reply with ONLY one word: YES or NO"
    )

    payload = json.dumps({
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 5,
        "temperature": 0,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "HTTP-Referer": "http://localhost:5000",
            "X-Title": "STEM Karaoke Kit Chatbot",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            answer = data["choices"][0]["message"]["content"].strip().upper()
            return answer.startswith("YES")
    except Exception as e:
        print(f"LLM scope check failed: {e}")
        return False


def generate_response(message: str, context: dict, kit_id: str = None) -> dict:
    """Generate a response: guardrails first, then LLM for in-scope queries."""
    kit = _get_kit(kit_id)
    steps = kit["steps"]

    # ── Guardrail: block out-of-scope queries ────────────────────────────────
    # Keyword check first (fast, free). If that fails, ask LLM as fallback.
    if not is_in_scope(message, kit_id):
        if not llm_scope_check(message, kit_id):
            return kit["guardrail_response"]

    # ── Find relevant steps for context & images ─────────────────────────────
    current_step = context.get("current_step", None)
    relevant_steps = find_relevant_steps(message, kit_id)
    query_type = classify_query(message)

    # Handle navigation intents locally (no LLM needed)
    nav_response = handle_navigation(message, current_step, kit_id)
    if nav_response:
        return nav_response

    # ── Build context for LLM ────────────────────────────────────────────────
    step_context = ""
    images = []

    if relevant_steps:
        for s in relevant_steps[:2]:
            if query_type == "concept":
                # For concept questions, emphasize science content
                step_context += (
                    f"\n--- Step {s['step_number']}: {s['title']} ---\n"
                    f"Topic: {s['topic']}\n"
                    f"Science concept: {s['science_concept']}\n"
                    f"Brief instructions: {s['detailed_instructions']}\n"
                )
            else:
                # For step/general questions, provide full instructions
                substeps_text = "\n".join([f"  {i+1}. {sub}" for i, sub in enumerate(s["sub_steps"])])
                tips = "\n".join([f"  - {t}" for t in s["safety_tips"]])
                step_context += (
                    f"\n--- Step {s['step_number']}: {s['title']} ---\n"
                    f"Topic: {s['topic']}\n"
                    f"Instructions: {s['detailed_instructions']}\n"
                    f"Sub-steps:\n{substeps_text}\n"
                    f"Safety tips:\n{tips}\n"
                    f"Tools needed: {', '.join(s['tools_needed'])}\n"
                )
            images.append({
                "url": s["image_url"],
                "caption": f"Step {s['step_number']}: {s['title']}"
            })
    elif current_step:
        s = steps[current_step - 1]
        substeps_text = "\n".join([f"  {i+1}. {sub}" for i, sub in enumerate(s["sub_steps"])])
        step_context = (
            f"\n--- Current Step {s['step_number']}: {s['title']} ---\n"
            f"Topic: {s['topic']}\n"
            f"Instructions: {s['detailed_instructions']}\n"
            f"Sub-steps:\n{substeps_text}\n"
            f"Science concept: {s['science_concept']}\n"
        )
        images.append({
            "url": s["image_url"],
            "caption": f"Step {s['step_number']}: {s['title']}"
        })

    # ── Call LLM via OpenRouter ──────────────────────────────────────────────
    llm_text = call_llm(message, step_context, current_step, query_type, kit_id)

    new_step = relevant_steps[0]["step_number"] if relevant_steps else current_step

    return {
        "text": llm_text,
        "images": images,
        "current_step": new_step
    }


def handle_navigation(message: str, current_step, kit_id: str = None) -> dict | None:
    """Handle simple navigation intents without LLM."""
    kit = _get_kit(kit_id)
    steps = kit["steps"]
    experiment_name = kit["experiment_name"]
    msg_lower = message.lower().strip()

    # Greeting
    if msg_lower in ["hi", "hello", "hey", "hey there", "greetings"]:
        return {
            "text": (
                f"Welcome to the **{experiment_name}** Assistant! 🔬🔊\n\n"
                "I'm your AI guide powered by real STEM knowledge. Ask me anything about the experiments!\n\n"
                "**I can help with:**\n"
                "• Step-by-step experiment instructions\n"
                "• Detailed **sub-steps** broken down further\n"
                "• **Science concepts** — NCERT connections (Class 6-10)\n"
                "• **Safety tips**, troubleshooting, and tools\n\n"
                "Try asking: *\"Tell me about experiment 1\"* or *\"What is a series circuit?\"* 🚀"
            ),
            "images": [],
            "current_step": None
        }

    # Thanks / bye
    if any(w in msg_lower for w in ["thank", "thanks", "bye", "goodbye"]):
        return {
            "text": f"Great job working on your **{experiment_name}**! 🎉 Keep experimenting and learning! 🔬✨",
            "images": [],
            "current_step": current_step
        }

    # List all steps
    if any(phrase in msg_lower for phrase in ["all steps", "list steps", "show steps", "overview", "list all", "show all", "all experiments", "list experiments"]):
        steps_list = "\n".join([f"  **Step {s['step_number']}:** {s['title']} — _{s['topic']}_" for s in steps])
        return {
            "text": f"Here are all **{len(steps)} steps/experiments** for the {experiment_name}:\n\n{steps_list}\n\nAsk me about any step for details!",
            "images": [],
            "current_step": current_step
        }

    # Next / Previous step
    if any(phrase in msg_lower for phrase in ["next step", "what's next", "after this", "next experiment"]):
        if current_step and current_step < len(steps):
            step = steps[current_step]
            return {
                "text": f"**Step {step['step_number']}: {step['title']}**\n\n{step['detailed_instructions']}",
                "images": [{"url": step["image_url"], "caption": f"Step {step['step_number']}: {step['title']}"}] if step["image_url"] else [],
                "current_step": step["step_number"]
            }
        elif current_step == len(steps):
            return {"text": "🎉 You've completed all steps! Great job!", "images": [], "current_step": current_step}

    if any(phrase in msg_lower for phrase in ["previous step", "go back", "before this", "previous experiment"]):
        if current_step and current_step > 1:
            step = steps[current_step - 2]
            return {
                "text": f"**Step {step['step_number']}: {step['title']}**\n\n{step['detailed_instructions']}",
                "images": [{"url": step["image_url"], "caption": f"Step {step['step_number']}: {step['title']}"}] if step["image_url"] else [],
                "current_step": step["step_number"]
            }

    return None  # Not a navigation intent


# ─── OpenRouter LLM Call ─────────────────────────────────────────────────────

def call_llm(user_message: str, step_context: str, current_step: int | None, query_type: str = "general", kit_id: str = None) -> str:
    """Call OpenRouter API with the user's question and relevant step context."""
    if not OPENROUTER_API_KEY or OPENROUTER_API_KEY == "your-openrouter-api-key-here":
        return _fallback_response(user_message, step_context, current_step, kit_id)

    kit = _get_kit(kit_id)
    system_prompt = kit["system_prompt"]
    num_steps = len(kit["steps"])

    messages = [
        {"role": "system", "content": system_prompt},
    ]

    # Add query-type hint so LLM knows how to respond
    if query_type == "concept":
        messages.append({
            "role": "system",
            "content": (
                "QUERY TYPE: CONCEPT/THEORY QUESTION.\n"
                "The student is asking about a science concept, theory, or principle. "
                "Focus your answer on explaining the science behind it — reference NCERT chapters, "
                "use analogies, and connect it to the experiment. Don't give assembly instructions "
                "unless briefly needed for context."
            )
        })
    elif query_type == "step":
        messages.append({
            "role": "system",
            "content": (
                "QUERY TYPE: STEP/INSTRUCTION QUESTION.\n"
                "The student is asking how to perform a specific assembly step or wants instructions. "
                "Focus on clear, actionable sub-steps and practical guidance. Mention safety tips and "
                "required tools. Keep science explanations brief unless asked."
            )
        })

    if step_context:
        messages.append({
            "role": "system",
            "content": f"RELEVANT STEP CONTEXT (use this to answer):\n{step_context}"
        })

    if current_step:
        messages.append({
            "role": "system",
            "content": f"The user is currently on Step {current_step} of {num_steps}."
        })

    messages.append({"role": "user", "content": user_message})

    payload = json.dumps({
        "model": LLM_MODEL,
        "messages": messages,
        "max_tokens": 600,
        "temperature": 0.5,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "HTTP-Referer": "http://localhost:5000",
            "X-Title": "STEM Karaoke Kit Chatbot",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"OpenRouter API error {e.code}: {error_body}")
        return _fallback_response(user_message, step_context, current_step, kit_id)
    except Exception as e:
        print(f"LLM call failed: {e}")
        return _fallback_response(user_message, step_context, current_step, kit_id)


def _fallback_response(user_message: str, step_context: str, current_step: int | None, kit_id: str = None) -> str:
    """Fallback when LLM is unavailable — use the pre-built knowledge base."""
    kit = _get_kit(kit_id)
    steps = kit["steps"]
    if step_context:
        # Return the step context formatted nicely
        return step_context.strip()
    if current_step and current_step <= len(steps):
        s = steps[current_step - 1]
        return f"**Step {s['step_number']}: {s['title']}**\n\n{s['detailed_instructions']}\n\n🔬 {s['science_concept']}"
    return (
        "I'm having trouble connecting to the AI service right now. "
        "But you can still ask about any specific step (e.g., 'Tell me about step 5') "
        "and I'll show you the instructions and images!"
    )


# ─── API Routes ──────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json()
    if not data or "message" not in data:
        return jsonify({"error": "No message provided"}), 400

    user_message = data["message"].strip()
    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    kit_id = data.get("kit_id", DEFAULT_KIT)
    if kit_id not in KITS:
        kit_id = DEFAULT_KIT

    # Limit message length to prevent abuse
    if len(user_message) > 500:
        return jsonify({
            "response": {
                "text": "Please keep your question shorter (under 500 characters). This helps me give you a more focused answer!",
                "images": [],
                "current_step": data.get("current_step")
            }
        })

    context = {"current_step": data.get("current_step")}
    response = generate_response(user_message, context, kit_id)

    return jsonify({"response": response})


@app.route("/api/steps", methods=["GET"])
def get_steps():
    """Return all steps with basic info for a given kit."""
    kit_id = request.args.get("kit", DEFAULT_KIT)
    kit = _get_kit(kit_id)
    steps_summary = [
        {
            "step_number": s["step_number"],
            "title": s["title"],
            "topic": s["topic"],
            "image_url": s["image_url"]
        }
        for s in kit["steps"]
    ]
    return jsonify({"steps": steps_summary, "experiment": kit["experiment_name"]})


@app.route("/api/step/<int:step_num>", methods=["GET"])
def get_step(step_num):
    """Return full details for a specific step."""
    kit_id = request.args.get("kit", DEFAULT_KIT)
    kit = _get_kit(kit_id)
    steps = kit["steps"]
    if step_num < 1 or step_num > len(steps):
        return jsonify({"error": "Invalid step number"}), 404
    step = steps[step_num - 1]
    return jsonify({"step": format_step_response(step, "normal")})


@app.route("/api/kits", methods=["GET"])
def get_kits():
    """Return list of available experiment kits."""
    kits_list = []
    for kid, kit in KITS.items():
        kits_list.append({
            "kit_id": kid,
            "name": kit["experiment_name"],
            "num_steps": len(kit["steps"]),
            "subject": kit["kb"].get("subject", ""),
            "grade": kit["kb"].get("grade_relevance", ""),
        })
    return jsonify({"kits": kits_list, "default": DEFAULT_KIT})


if __name__ == "__main__":
    print(f"\n🔬 STEM Education Chatbot — Multi-Kit")
    print("=" * 50)
    for kid, kit in KITS.items():
        print(f"  📦 {kid}: {kit['experiment_name']} ({len(kit['steps'])} steps)")
    if OPENROUTER_API_KEY and OPENROUTER_API_KEY != "your-openrouter-api-key-here":
        print(f"✅ LLM: {LLM_MODEL} via OpenRouter")
    else:
        print("⚠️  No OpenRouter API key — running in fallback mode")
        print("   Add your key to .env: OPENROUTER_API_KEY=sk-or-...")
    print("Open http://127.0.0.1:5000 in your browser\n")
    app.run(debug=True, port=5000)
