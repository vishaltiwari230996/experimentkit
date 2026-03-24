"""
Karaoke Speaker Kit - STEM Education Chatbot
Flask backend with LLM-powered Q&A (OpenRouter), guardrails, and image support.
Deployed as Vercel serverless function.
"""

import os
import json
import re
import urllib.request
import urllib.error
from flask import Flask, request, jsonify, render_template

# ─── Paths (resolve relative to project root, not api/) ──────────────────────
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = Flask(
    __name__,
    static_folder=os.path.join(ROOT_DIR, "static"),
    template_folder=os.path.join(ROOT_DIR, "templates"),
    static_url_path="/static",
)

# ─── Load .env file (local dev only; Vercel uses env vars) ───────────────────
ENV_PATH = os.path.join(ROOT_DIR, ".env")
if os.path.exists(ENV_PATH):
    with open(ENV_PATH, "r") as ef:
        for line in ef:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

# ─── Load knowledge base ─────────────────────────────────────────────────────
KNOWLEDGE_BASE_PATH = os.path.join(ROOT_DIR, "knowledge_base.json")
with open(KNOWLEDGE_BASE_PATH, "r", encoding="utf-8") as f:
    KB = json.load(f)

STEPS = KB["steps"]
EXPERIMENT_NAME = KB["experiment"]
COMPONENTS = KB["components"]
NCERT_CONNECTIONS = KB["ncert_connections"]
LEARNING_OBJECTIVES = KB["learning_objectives"]

# Build keyword index for fast lookup
KEYWORD_INDEX = {}
for step in STEPS:
    for kw in step["keywords"]:
        KEYWORD_INDEX[kw.lower()] = step["step_number"]
    KEYWORD_INDEX[step["title"].lower()] = step["step_number"]
    KEYWORD_INDEX[step["topic"].lower()] = step["step_number"]
    KEYWORD_INDEX[f"step {step['step_number']}"] = step["step_number"]
    KEYWORD_INDEX[f"step{step['step_number']}"] = step["step_number"]

# ─── OpenRouter LLM Model ────────────────────────────────────────────────────
LLM_MODEL = "google/gemini-2.0-flash-lite-001"

# Scope-related keywords for guardrail detection
SCOPE_KEYWORDS = [
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
]


def _word_match(keyword: str, text: str) -> bool:
    """Match keyword in text using word boundaries for short words."""
    if len(keyword) <= 3:
        return bool(re.search(r'\b' + re.escape(keyword) + r'\b', text))
    return keyword in text


def is_in_scope(message: str) -> bool:
    """Check if user message is within the experiment/STEM scope."""
    msg_lower = message.lower().strip()

    greetings = ["hi", "hello", "hey", "thanks", "thank you", "bye", "ok", "okay", "help", "start"]
    if msg_lower in greetings:
        return True

    if re.search(r"step\s*\d+", msg_lower):
        return True

    for kw in SCOPE_KEYWORDS:
        if _word_match(kw, msg_lower):
            return True

    experiment_terms = [
        "speaker", "karaoke", "build", "assemble", "step", "wire",
        "board", "battery", "panel", "screw", "switch", "mic",
        "volume", "knob", "port", "charge", "bluetooth", "connect",
        "circuit", "sound", "this", "experiment",
        "kit", "project", "next", "previous", "potentiometer", "pcb",
        "enclosure", "wooden", "wood", "driver", "cone", "magnet",
        "amplifier", "frequency", "vibration", "current", "voltage",
        "resistance", "polarity", "lithium", "rechargeable", "watt",
    ]
    question_patterns = [
        r"how (do|to|does|can|should)",
        r"what (is|are|does|do|should)",
        r"why (is|are|do|does|should)",
        r"where (is|are|do|does|should)",
        r"which (step|part|component|wire|panel)",
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

    strong_terms = [
        "speaker", "karaoke", "bluetooth", "pcb", "circuit", "battery",
        "panel", "screw", "switch", "mic", "microphone", "volume", "knob",
        "potentiometer", "wire", "solder", "connector", "assembly", "step",
        "experiment", "kit", "build", "ncert", "stem",
    ]
    for term in strong_terms:
        if _word_match(term, msg_lower):
            return True

    return False


def find_relevant_steps(message: str) -> list:
    """Find steps relevant to the user's message using keyword matching."""
    msg_lower = message.lower().strip()
    matched_steps = {}

    step_nums = re.findall(r"step\s*(\d+)", msg_lower)
    for num_str in step_nums:
        num = int(num_str)
        if 1 <= num <= len(STEPS):
            matched_steps[num] = 100

    for kw, step_num in KEYWORD_INDEX.items():
        if kw in msg_lower:
            score = len(kw) * 2
            if step_num in matched_steps:
                matched_steps[step_num] = max(matched_steps[step_num], score)
            else:
                matched_steps[step_num] = score

    words = re.findall(r'\b\w+\b', msg_lower)
    for step in STEPS:
        step_text = f"{step['title']} {step['topic']} {' '.join(step['keywords'])}".lower()
        for word in words:
            if len(word) > 3 and word in step_text:
                sn = step["step_number"]
                matched_steps[sn] = matched_steps.get(sn, 0) + 1

    sorted_steps = sorted(matched_steps.items(), key=lambda x: x[1], reverse=True)
    return [STEPS[sn - 1] for sn, _ in sorted_steps[:3]]


# ─── Query Classification ────────────────────────────────────────────────────

def classify_query(message: str) -> str:
    """Classify whether the user is asking a concept/theory question or a step/instruction question."""
    msg_lower = message.lower().strip()

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
    else:
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


def generate_response(message: str, context: dict) -> dict:
    """Generate a response: guardrails first, then LLM for in-scope queries."""
    msg_lower = message.lower().strip()

    if not is_in_scope(message):
        return {
            "text": (
                "I appreciate your curiosity! However, I'm specifically designed to help you with the **Karaoke Speaker Kit** assembly experiment. "
                "I can assist you with:\n\n"
                "• 🔧 **Assembly steps** — detailed instructions for each of the 23 steps\n"
                "• 📋 **Sub-steps** — breaking down any step into smaller, easier actions\n"
                "• 🔬 **Science concepts** — the NCERT-related physics & electronics behind each step\n"
                "• ⚠️ **Safety tips** — precautions for each step\n"
                "• 🖼️ **Step images** — visual guides for assembly\n"
                "• 🧰 **Components & tools** — what you need\n\n"
                "Please ask me something about the experiment, and I'll be happy to help! 😊"
            ),
            "images": [],
            "is_guardrail": True
        }

    current_step = context.get("current_step", None)
    relevant_steps = find_relevant_steps(message)
    query_type = classify_query(message)

    nav_response = handle_navigation(message, current_step)
    if nav_response:
        return nav_response

    step_context = ""
    images = []

    if relevant_steps:
        for s in relevant_steps[:2]:
            if query_type == "concept":
                step_context += (
                    f"\n--- Step {s['step_number']}: {s['title']} ---\n"
                    f"Topic: {s['topic']}\n"
                    f"Science concept: {s['science_concept']}\n"
                    f"Brief instructions: {s['detailed_instructions']}\n"
                )
            else:
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
        s = STEPS[current_step - 1]
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

    llm_text = call_llm(message, step_context, current_step, query_type)

    new_step = relevant_steps[0]["step_number"] if relevant_steps else current_step

    return {
        "text": llm_text,
        "images": images,
        "current_step": new_step
    }


def handle_navigation(message: str, current_step) -> dict | None:
    """Handle simple navigation intents without LLM."""
    msg_lower = message.lower().strip()

    if msg_lower in ["hi", "hello", "hey", "hey there", "greetings"]:
        return {
            "text": (
                f"Welcome to the **{EXPERIMENT_NAME}** Assembly Assistant! 🎤🔊\n\n"
                "I'm your AI guide powered by real STEM knowledge. Ask me anything about building your karaoke speaker!\n\n"
                "**I can help with:**\n"
                "• Step-by-step assembly instructions with images\n"
                "• Detailed **sub-steps** broken down further\n"
                "• **Science concepts** — NCERT connections (Class 6-10)\n"
                "• **Safety tips**, troubleshooting, and tools\n\n"
                "Try asking: *\"How do I connect the speaker wires?\"* or *\"What is a potentiometer?\"* 🚀"
            ),
            "images": [],
            "current_step": None
        }

    if any(w in msg_lower for w in ["thank", "thanks", "bye", "goodbye"]):
        return {
            "text": "Great job working on your Karaoke Speaker Kit! 🎉 Keep experimenting and learning! 🔬✨",
            "images": [],
            "current_step": current_step
        }

    if any(phrase in msg_lower for phrase in ["all steps", "list steps", "show steps", "overview", "list all", "show all"]):
        steps_list = "\n".join([f"  **Step {s['step_number']}:** {s['title']} — _{s['topic']}_" for s in STEPS])
        return {
            "text": f"Here are all **23 assembly steps** for the {EXPERIMENT_NAME}:\n\n{steps_list}\n\nAsk me about any step for details!",
            "images": [],
            "current_step": current_step
        }

    if any(phrase in msg_lower for phrase in ["next step", "what's next", "after this"]):
        if current_step and current_step < len(STEPS):
            step = STEPS[current_step]
            return {
                "text": f"**Step {step['step_number']}: {step['title']}**\n\n{step['detailed_instructions']}",
                "images": [{"url": step["image_url"], "caption": f"Step {step['step_number']}: {step['title']}"}],
                "current_step": step["step_number"]
            }
        elif current_step == len(STEPS):
            return {"text": "🎉 You've completed all steps! Your speaker is ready!", "images": [], "current_step": current_step}

    if any(phrase in msg_lower for phrase in ["previous step", "go back", "before this"]):
        if current_step and current_step > 1:
            step = STEPS[current_step - 2]
            return {
                "text": f"**Step {step['step_number']}: {step['title']}**\n\n{step['detailed_instructions']}",
                "images": [{"url": step["image_url"], "caption": f"Step {step['step_number']}: {step['title']}"}],
                "current_step": step["step_number"]
            }

    return None


# ─── OpenRouter LLM Call ─────────────────────────────────────────────────────

SYSTEM_PROMPT = f"""You are a friendly STEM education assistant for the "{EXPERIMENT_NAME}" experiment kit. 
This is a hands-on DIY kit where students (Class 6-10) build a Bluetooth karaoke speaker from scratch.

STRICT RULES:
1. ONLY answer questions related to this experiment, its assembly steps, components, science concepts (NCERT), and STEM education.
2. If the user asks ANYTHING unrelated (politics, movies, general knowledge, coding, etc.), politely say: "I can only help with the Karaoke Speaker Kit experiment. Please ask me about assembly steps, science concepts, or troubleshooting!"
3. Keep answers concise, student-friendly, and encouraging.
4. Use **bold** for important terms and step numbers.
5. When explaining science concepts, reference NCERT chapters where applicable.
6. If the user asks for sub-steps or more detail, break the step into smaller numbered actions.
7. Always be encouraging — this is a learning experience for young students.

EXPERIMENT OVERVIEW:
- 23 assembly steps to build a Bluetooth karaoke speaker
- Components: wooden panels, speaker driver, Bluetooth PCB, mic jack, Type-C charging, rechargeable battery, power switch, potentiometer, volume knob, wires, screws
- NCERT connections: Sound (Class 8), Electricity (Class 10), Magnetic Effects (Class 10), Energy conversion (Class 9)
- Key concepts: electromagnetic induction, circuits, Ohm's law, sound waves, energy conversion"""


def call_llm(user_message: str, step_context: str, current_step: int | None, query_type: str = "general") -> str:
    """Call OpenRouter API with the user's question and relevant step context."""
    if not OPENROUTER_API_KEY or OPENROUTER_API_KEY == "your-openrouter-api-key-here":
        return _fallback_response(user_message, step_context, current_step)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
    ]

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
            "content": f"The user is currently on Step {current_step} of 23."
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
            "HTTP-Referer": "https://stem-karaoke-kit.vercel.app",
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
        return _fallback_response(user_message, step_context, current_step)
    except Exception as e:
        print(f"LLM call failed: {e}")
        return _fallback_response(user_message, step_context, current_step)


def _fallback_response(user_message: str, step_context: str, current_step: int | None) -> str:
    """Fallback when LLM is unavailable — use the pre-built knowledge base."""
    if step_context:
        return step_context.strip()
    if current_step:
        s = STEPS[current_step - 1]
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

    if len(user_message) > 500:
        return jsonify({
            "response": {
                "text": "Please keep your question shorter (under 500 characters). This helps me give you a more focused answer!",
                "images": [],
                "current_step": data.get("current_step")
            }
        })

    context = {"current_step": data.get("current_step")}
    response = generate_response(user_message, context)

    return jsonify({"response": response})


@app.route("/api/steps", methods=["GET"])
def get_steps():
    """Return all steps with basic info."""
    steps_summary = [
        {
            "step_number": s["step_number"],
            "title": s["title"],
            "topic": s["topic"],
            "image_url": s["image_url"]
        }
        for s in STEPS
    ]
    return jsonify({"steps": steps_summary, "experiment": EXPERIMENT_NAME})


@app.route("/api/step/<int:step_num>", methods=["GET"])
def get_step(step_num):
    """Return full details for a specific step."""
    if step_num < 1 or step_num > len(STEPS):
        return jsonify({"error": "Invalid step number"}), 404
    step = STEPS[step_num - 1]
    return jsonify({"step": format_step_response(step, "normal")})
