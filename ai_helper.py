"""
AI Copilot for DevTracker.

Generates context-aware advice for an application depending on its current
status:
  - applied / oa / interview  -> how to prepare
  - rejected                  -> what likely went wrong + resume/interview
                                  improvements
  - offer                     -> negotiation pointers

Uses Google's Gemini API (free tier, no credit card required) when
GOOGLE_API_KEY is set in the environment. If no key is configured, falls
back to a clearly-labelled template response so the feature never crashes
or blocks a live demo.

Get a free key at: https://aistudio.google.com/apikey
"""

import os
import json
import urllib.request
import urllib.error

GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
)

SYSTEM_PROMPT = (
    "You are a career coach helping a student or new grad with their job "
    "search. Be specific, concise, and practical. Use short bullet points, "
    "not long paragraphs. Never invent facts about the company you are not "
    "given."
)


def _call_gemini(prompt, system_instruction=None, max_tokens=400):
    """
    Makes a single request to the Gemini API. Returns the generated text.
    Raises on any failure (network, bad key, bad response shape) — callers
    are responsible for catching and falling back.
    """
    api_key = os.environ.get('GOOGLE_API_KEY')
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY not set")

    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": max_tokens},
    }
    if system_instruction:
        body["systemInstruction"] = {"parts": [{"text": system_instruction}]}

    req = urllib.request.Request(
        f"{GEMINI_URL}?key={api_key}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    return data["candidates"][0]["content"]["parts"][0]["text"].strip()


def _fallback_advice(status, company_name, role_title):
    """A rule-based placeholder used when no API key is configured."""
    if status in ('applied', 'oa'):
        return (
            "• Research {company}'s recent products/news so you can speak to "
            "them if asked \"why us?\"\n"
            "• Review the core skills listed in the {role} posting and refresh "
            "the ones you're rustiest on\n"
            "• Prepare a 60-second walkthrough of one project relevant to this role\n\n"
            "(This is placeholder advice — connect a free GOOGLE_API_KEY to "
            "generate advice tailored to this specific application.)"
        ).format(company=company_name, role=role_title)

    if status == 'interview':
        return (
            "• Practice 2-3 STAR-format stories (situation, task, action, result) "
            "relevant to {role}\n"
            "• Prepare 2 thoughtful questions to ask the interviewer about the team\n"
            "• Do a mock technical/behavioral round if this is a technical role\n\n"
            "(Placeholder advice — connect a free GOOGLE_API_KEY for tailored prep.)"
        ).format(role=role_title)

    if status == 'rejected':
        return (
            "• Ask (politely, by email) if the recruiter can share one area for improvement\n"
            "• Re-check your resume's bullet points for measurable impact (numbers, outcomes)\n"
            "• Log what round you were rejected at — it tells you what to strengthen next time\n\n"
            "(Placeholder feedback — connect a free GOOGLE_API_KEY for advice "
            "tailored to this specific rejection.)"
        )

    if status == 'offer':
        return (
            "• Compare the total compensation, not just base salary\n"
            "• It's normal to ask for a few days to decide and to ask if there's "
            "flexibility on comp\n"
            "• Get the offer details in writing before declining any other processes\n\n"
            "(Placeholder tips — connect a free GOOGLE_API_KEY for tailored advice.)"
        )

    return "No advice available for this status yet."


def generate_ai_notes(company_name, role_title, status, notes=None, resume_summary=None):
    """
    Returns a short block of AI-generated advice text for this application.
    Falls back to a template if no API key is set or the call fails, so this
    never raises and never blocks the rest of the app.
    """
    if not os.environ.get('GOOGLE_API_KEY'):
        return _fallback_advice(status, company_name, role_title)

    try:
        status_instruction = {
            'applied': 'The user just applied. Give prep tips for the OA/interview stages they might face next.',
            'oa': 'The user has an online assessment coming up. Give focused OA prep tips.',
            'interview': 'The user has an interview coming up. Give focused interview prep tips.',
            'rejected': 'The user was rejected. Give constructive feedback on likely gaps and concrete resume/interview improvements.',
            'offer': 'The user received an offer. Give brief negotiation and decision-making pointers.',
        }.get(status, 'Give general job search advice.')

        prompt = (
            f"Company: {company_name}\n"
            f"Role: {role_title}\n"
            f"Current status: {status}\n"
            f"User's notes: {notes or 'none'}\n"
            f"Resume summary: {resume_summary or 'not provided'}\n\n"
            f"{status_instruction}\n"
            "Respond in under 120 words, as short bullet points."
        )

        return _call_gemini(prompt, system_instruction=SYSTEM_PROMPT)

    except Exception as exc:  # noqa: BLE001 - never let this break the page
        return (
            f"(AI generation failed: {exc}. Showing fallback advice instead.)\n\n"
            + _fallback_advice(status, company_name, role_title)
        )


def parse_bulk_applications(raw_text):
    """
    Takes freeform pasted text (e.g. copied from an Internshala/LinkedIn
    "My Applications" page) and returns a list of dicts:
    [{"company_name": ..., "role_title": ..., "location": ..., "applied_date": ...}, ...]

    Uses the Gemini API when available. Falls back to a simple line-based
    heuristic parser otherwise, so bulk import still works (just less
    accurately) without an API key.
    """
    if os.environ.get('GOOGLE_API_KEY'):
        try:
            prompt = (
                "The following text was copied and pasted from a job/internship "
                "application tracking page (e.g. Internshala, LinkedIn). Extract "
                "every distinct application as a JSON array of objects with keys: "
                "company_name, role_title, location (or null), applied_date "
                "(YYYY-MM-DD, or null if not present). "
                "Respond with ONLY the JSON array, no other text, no markdown fences.\n\n"
                f"TEXT:\n{raw_text}"
            )

            text = _call_gemini(prompt, max_tokens=2000)
            text = text.replace('```json', '').replace('```', '').strip()
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass  # fall through to heuristic parser

    return _heuristic_parse(raw_text)


def _heuristic_parse(raw_text):
    """
    Very simple fallback: treats each non-empty line as one application,
    splitting on common separators. Not accurate, but keeps the feature
    usable with zero API key.
    """
    results = []
    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue

        for sep in ['\t', ' - ', ' – ', '|']:
            if sep in line:
                parts = [p.strip() for p in line.split(sep) if p.strip()]
                if len(parts) >= 2:
                    results.append({
                        'company_name': parts[0],
                        'role_title': parts[1],
                        'location': parts[2] if len(parts) > 2 else None,
                        'applied_date': None,
                    })
                    break
        else:
            results.append({
                'company_name': line,
                'role_title': 'Unspecified role',
                'location': None,
                'applied_date': None,
            })

    return results


def answer_question(question, context=None):
    """
    General-purpose career Q&A for the floating 'Ask DevTracker' widget.
    context is an optional short string summarizing the user's applications.
    """
    if not os.environ.get('GOOGLE_API_KEY'):
        return (
            "The AI assistant isn't connected yet — add a free GOOGLE_API_KEY "
            "(get one at aistudio.google.com/apikey) to enable real answers. "
            "For now: browse your dashboard, or check the AI Copilot panel "
            "on each application for prep tips and feedback."
        )

    try:
        system = (
            "You are the in-app assistant for DevTracker, a job/internship "
            "application tracker. Answer the user's question about their job "
            "search, interview prep, resumes, or how to use the app. Be "
            "concise — a few sentences or a short bullet list, not an essay."
        )

        prompt = question
        if context:
            prompt = f"Context on my applications: {context}\n\nQuestion: {question}"

        return _call_gemini(prompt, system_instruction=system)

    except Exception as exc:  # noqa: BLE001
        return f"Sorry, something went wrong asking the AI ({exc}). Try again in a moment."
