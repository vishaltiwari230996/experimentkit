/**
 * Karaoke Speaker Kit — STEM Chatbot Frontend
 */

const chatMessages = document.getElementById("chatMessages");
const userInput = document.getElementById("userInput");
const sendBtn = document.getElementById("sendBtn");
const stepList = document.getElementById("stepList");
const headerStep = document.getElementById("headerStep");
const quickActions = document.getElementById("quickActions");
const mobileMenu = document.getElementById("mobileMenu");
const sidebar = document.getElementById("sidebar");
const resetBtn = document.getElementById("resetBtn");
const sidebarOverlay = document.getElementById("sidebarOverlay");

let currentStep = null;
let isLoading = false;

// ─── Initialize ─────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
    loadStepsSidebar();
    addBotMessage(
        "Welcome to the **Karaoke Speaker Kit** Assembly Assistant! 🎤🔊\n\n" +
        "I'll guide you through building your own Bluetooth karaoke speaker — a hands-on STEM experiment linked to NCERT Science.\n\n" +
        "**I can help you with:**\n" +
        "• Step-by-step assembly instructions with images\n" +
        "• Detailed **sub-steps** for any step\n" +
        "• **Science concepts** (NCERT connections)\n" +
        "• **Safety tips** and required tools\n" +
        "• Troubleshooting help\n\n" +
        "Try the quick buttons below, or ask me anything about the experiment!",
        []
    );
});

// ─── Sidebar Steps ──────────────────────────────────────────────

async function loadStepsSidebar() {
    try {
        const res = await fetch("/api/steps");
        const data = await res.json();
        stepList.innerHTML = "";
        data.steps.forEach((step) => {
            const div = document.createElement("div");
            div.className = "step-item";
            div.dataset.step = step.step_number;
            div.innerHTML = `
                <div class="step-number">${step.step_number}</div>
                <div class="step-info">
                    <div class="step-title">${escapeHTML(step.title)}</div>
                    <div class="step-topic">${escapeHTML(step.topic)}</div>
                </div>
            `;
            div.addEventListener("click", () => {
                sendMessage(`Tell me about step ${step.step_number}`);
                closeSidebar();
            });
            stepList.appendChild(div);
        });
    } catch (e) {
        console.error("Failed to load steps:", e);
    }
}

function highlightStep(stepNum) {
    document.querySelectorAll(".step-item").forEach((el) => {
        el.classList.toggle("active", parseInt(el.dataset.step) === stepNum);
    });
    if (stepNum) {
        headerStep.innerHTML = `<span>Step ${stepNum} of 23</span>`;
    }
}

// ─── Mobile Sidebar ─────────────────────────────────────────────

mobileMenu.addEventListener("click", () => {
    sidebar.classList.toggle("open");
    sidebarOverlay.classList.toggle("active");
});

sidebarOverlay.addEventListener("click", closeSidebar);

function closeSidebar() {
    sidebar.classList.remove("open");
    sidebarOverlay.classList.remove("active");
}

// ─── Reset Chat ─────────────────────────────────────────────────

resetBtn.addEventListener("click", resetChat);

function resetChat() {
    currentStep = null;
    chatMessages.innerHTML = "";
    headerStep.innerHTML = "<span>No step selected</span>";
    document.querySelectorAll(".step-item").forEach((el) => el.classList.remove("active"));
    addBotMessage(
        "Chat has been reset! 🔄\n\n" +
        "Welcome back to the **Karaoke Speaker Kit** Assembly Assistant! 🎤🔊\n\n" +
        "Ask me anything about the experiment — assembly steps, science concepts, safety tips, or troubleshooting!",
        []
    );
    updateQuickActions();
}

// ─── Chat ───────────────────────────────────────────────────────

sendBtn.addEventListener("click", () => {
    const msg = userInput.value.trim();
    if (msg && !isLoading) sendMessage(msg);
});

userInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        const msg = userInput.value.trim();
        if (msg && !isLoading) sendMessage(msg);
    }
});

// Auto-resize textarea
userInput.addEventListener("input", () => {
    userInput.style.height = "auto";
    userInput.style.height = Math.min(userInput.scrollHeight, 120) + "px";
});

// Quick action buttons
quickActions.addEventListener("click", (e) => {
    const btn = e.target.closest(".quick-btn");
    if (btn && !isLoading) {
        sendMessage(btn.dataset.msg);
    }
});

async function sendMessage(text) {
    if (isLoading) return;
    isLoading = true;
    sendBtn.disabled = true;

    addUserMessage(text);
    userInput.value = "";
    userInput.style.height = "auto";

    const typingEl = addTypingIndicator();

    try {
        const res = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                message: text,
                current_step: currentStep,
            }),
        });

        const data = await res.json();
        removeTypingIndicator(typingEl);

        if (data.response) {
            const resp = data.response;

            if (resp.current_step) {
                currentStep = resp.current_step;
                highlightStep(currentStep);
            }

            addBotMessage(resp.text, resp.images || [], resp.is_guardrail);

            // Update quick actions contextually
            updateQuickActions();
        }
    } catch (err) {
        removeTypingIndicator(typingEl);
        addBotMessage("Sorry, something went wrong. Please try again.", []);
        console.error(err);
    }

    isLoading = false;
    sendBtn.disabled = false;
    userInput.focus();
}

// ─── Message Rendering ──────────────────────────────────────────

function addUserMessage(text) {
    const div = document.createElement("div");
    div.className = "message user";
    div.innerHTML = `
        <div class="message-avatar">🧑</div>
        <div class="message-content">${escapeHTML(text)}</div>
    `;
    chatMessages.appendChild(div);
    scrollToBottom();
}

function addBotMessage(text, images = [], isGuardrail = false) {
    const div = document.createElement("div");
    div.className = "message bot";

    let guardrailBadge = "";
    if (isGuardrail) {
        guardrailBadge = `<div class="guardrail-badge">⚡ Scope Notice</div>`;
    }

    let imagesHTML = "";
    if (images && images.length > 0) {
        imagesHTML = `<div class="step-images">`;
        images.forEach((img) => {
            imagesHTML += `
                <div class="step-image-card">
                    <img src="${escapeAttr(img.url)}" alt="${escapeAttr(img.caption)}" loading="lazy" onerror="this.parentElement.style.display='none'">
                    <div class="image-caption">${escapeHTML(img.caption)}</div>
                </div>
            `;
        });
        imagesHTML += `</div>`;
    }

    div.innerHTML = `
        <div class="message-avatar">🤖</div>
        <div class="message-content">
            ${guardrailBadge}
            ${renderMarkdown(text)}
            ${imagesHTML}
        </div>
    `;
    chatMessages.appendChild(div);
    scrollToBottom();
}

function addTypingIndicator() {
    const div = document.createElement("div");
    div.className = "message bot typing-msg";
    div.innerHTML = `
        <div class="message-avatar">🤖</div>
        <div class="message-content">
            <div class="typing-indicator">
                <span></span><span></span><span></span>
            </div>
        </div>
    `;
    chatMessages.appendChild(div);
    scrollToBottom();
    return div;
}

function removeTypingIndicator(el) {
    if (el && el.parentNode) el.parentNode.removeChild(el);
}

function scrollToBottom() {
    requestAnimationFrame(() => {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    });
}

// ─── Quick Actions Update ───────────────────────────────────────

function updateQuickActions() {
    let buttons = [];
    if (currentStep) {
        buttons.push({ label: "📝 Sub-steps", msg: `Show sub-steps for step ${currentStep}` });
        buttons.push({ label: "🔬 Concept", msg: `What is the science concept for step ${currentStep}?` });
        buttons.push({ label: "⚠️ Safety", msg: `Safety tips for step ${currentStep}` });
        if (currentStep < 23) {
            buttons.push({ label: "➡️ Next Step", msg: "Next step" });
        }
        if (currentStep > 1) {
            buttons.push({ label: "⬅️ Previous", msg: "Previous step" });
        }
    } else {
        buttons.push({ label: "📋 All Steps", msg: "Show all steps" });
        buttons.push({ label: "🚀 Start", msg: "Start from step 1" });
        buttons.push({ label: "🧰 Components", msg: "What components are in the kit?" });
        buttons.push({ label: "📖 Learning", msg: "What will I learn from this experiment?" });
    }

    quickActions.innerHTML = buttons
        .map((b) => `<button class="quick-btn" data-msg="${escapeAttr(b.msg)}">${b.label}</button>`)
        .join("");
}

// ─── Markdown-like Rendering ────────────────────────────────────

function renderMarkdown(text) {
    let html = escapeHTML(text);

    // Headers: ### text
    html = html.replace(/^### (.+)$/gm, '<h4 style="margin:8px 0 4px;color:var(--accent-light)">$1</h4>');
    html = html.replace(/^## (.+)$/gm, '<h3 style="margin:10px 0 4px;color:var(--accent-light)">$1</h3>');

    // Bold: **text**
    html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

    // Italic: *text* or _text_
    html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");
    html = html.replace(/_(.+?)_/g, "<em>$1</em>");

    // Numbered lists: "1. item" at start of line
    html = html.replace(/^(\d+)\.\s+(.+)$/gm, '<div style="margin-left:12px">$1. $2</div>');

    // Bullet lists: "- item" or "• item"
    html = html.replace(/^[-•]\s+(.+)$/gm, '<div style="margin-left:12px">• $1</div>');

    // Line breaks
    html = html.replace(/\n/g, "<br>");

    // Clean up double <br> from list items
    html = html.replace(/<br><div/g, "<div");
    html = html.replace(/<\/div><br>/g, "</div>");

    return html;
}

// ─── Sanitization ───────────────────────────────────────────────

function escapeHTML(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

function escapeAttr(str) {
    return str
        .replace(/&/g, "&amp;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
}
