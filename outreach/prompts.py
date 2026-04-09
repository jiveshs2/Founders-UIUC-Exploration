"""Built-in organization context and prompt templates for Founders @ UIUC."""

from __future__ import annotations

# Shown to Groq for extraction + email generation
ORGANIZATION_CONTEXT = """Founders is the leading non-profit student entrepreneurship organization at the University of Illinois. Our mission is to grow and foster a community of continuous innovation and entrepreneurship at the University of Illinois. To do this, Founders hosts a number of events and offers resources to students interested in creating or developing a startup. Strong partnerships with universities and organizations across the country allows Founders to create a robust and valuable experience for student entrepreneurs not only at Illinois, but on campuses throughout the country."""

# UI + validation: selectable email tones
TONE_OPTIONS: tuple[str, ...] = (
    "formal",
    "professional",
    "friendly",
    "warm",
    "casual",
    "conversational",
    "personable",
    "persuasive",
    "urgent",
    "call-to-action focused",
    "motivational",
    "sales / pitch style",
    "informative",
    "neutral",
    "straightforward",
    "matter-of-fact",
    "academic",
    "research-oriented",
    "technical",
    "excited / enthusiastic",
    "energetic",
    "community-oriented",
    "inclusive",
    "promotional",
    "respectful",
    "direct",
    "inspirational",
    "storytelling",
    "gratitude-focused",
    "reflective",
    "urgent but polite",
)

DEFAULT_TONES: tuple[str, ...] = ("professional", "warm", "direct")


def normalize_tones(selected: list[str] | None) -> list[str]:
    """Keep only known tones, preserve order; if empty, use defaults."""
    if not selected:
        return list(DEFAULT_TONES)
    allowed = {t.lower() for t in TONE_OPTIONS}
    out: list[str] = []
    for t in selected:
        key = (t or "").strip().lower()
        if key in allowed and key not in out:
            out.append(key)
    return out if out else list(DEFAULT_TONES)


def build_extract_prompt(scope_hint: str) -> str:
    """User supplies only *who* to include; schema is fixed in the extraction system prompt."""
    scope = (scope_hint or "").strip()
    return f"""Include only companies/startups on the page that match this (follow strictly):
{scope}"""


def build_purpose_prompt(event_description: str, whats_in_it_for_them: str, tones: list[str]) -> str:
    event = (event_description or "").strip()
    benefit = (whats_in_it_for_them or "").strip()
    tone_list = normalize_tones(tones)
    tone_str = ", ".join(tone_list)

    return f"""Who we are (use this voice and credibility when writing):
{ORGANIZATION_CONTEXT}

Your task: draft outreach emails inviting or engaging the lead about the following.

Event / ask (be specific and clear):
{event}

What's in it for them to come? (make this concrete, lead-focused, and specific):
{benefit}

Tone for the email — blend these styles naturally: {tone_str}.

Rules:
- You represent Founders at the University of Illinois (student-led non-profit).
- Be respectful of the recipient's time; one clear ask.
- Do not invent facts about their company beyond what is in the lead context.
"""


def build_generation_system_prompt() -> str:
    return f"""You write concise, professional outreach emails on behalf of Founders, the student entrepreneurship organization at the University of Illinois.

Organization (for accurate voice):
{ORGANIZATION_CONTEXT}

Output ONLY a JSON object with keys "subject" and "body" (plain text, no HTML). No markdown fences.

Subject rules:
- The subject must be ONLY the event / ask (a short title).
- Do NOT include the value proposition / "what's in it for them" in the subject.

EMAIL BODY STRUCTURE (follow this exact order):

1. GREETING: "Dear [Founder Name or Company Name]," followed by a blank line. If founder name is known use it, otherwise use company name.

2. PLEASANTRY: "I hope this email finds you well." (exactly this line)

3. INTRO (1 sentence): State that you are a member of Founders at the University of Illinois (UIUC). Keep it brief, e.g. "I am reaching out on behalf of Founders, a student entrepreneurship organization at the University of Illinois."

4. EVENT (1 sentence): Clearly explain the event or ask.

5. RELEVANCE (1-2 sentences): Link the event to the recipient's company — reference what they do or their industry and explain why this is relevant to them. Use ONLY the lead context (company name, industry, notes, website). If unknown, use a generic-but-honest sentence like "Given your work in [industry], we believe this is relevant to you." Do NOT invent specifics about their company.

6. ASK (1 sentence): Ask them to participate / attend / be involved.

7. CLOSING (1 sentence): Express that you look forward to hearing back from them.

Formatting rules:
- Put a blank line after the greeting.
- Use a blank line between paragraphs where it aids readability.
- Do NOT use bullet points or numbered lists.
- Do NOT repeat yourself across sentences.
- Do NOT invent facts about their company beyond what is in the lead context."""
