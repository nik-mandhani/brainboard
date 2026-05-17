from fastapi import FastAPI, Request, Response, BackgroundTasks
from supabase import create_client
from openai import OpenAI
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client as TwilioClient
from dotenv import load_dotenv

import os
import re
import json
import html as html_lib
import requests
from urllib.parse import unquote, urlparse

load_dotenv()

app = FastAPI()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_KEY")
    or os.getenv("SUPABASE_ANON_KEY")
)
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN) if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN else None


def log_startup_config():
    missing = []

    if not OPENAI_API_KEY:
        missing.append("OPENAI_API_KEY")
    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not SUPABASE_KEY:
        missing.append("SUPABASE_SERVICE_ROLE_KEY or SUPABASE_KEY")

    if missing:
        print("Startup config warning: missing env vars ->", ", ".join(missing))

    if SUPABASE_KEY and SUPABASE_KEY.startswith("sb_publishable_"):
        print("Warning: use SUPABASE_SERVICE_ROLE_KEY on backend for reliable inserts.")

    if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN):
        print("Startup config warning: Twilio credentials missing.")


log_startup_config()


@app.get("/")
def home():
    return {"status": "Brainboard server is running"}


def clean_url(url):
    if not url:
        return None

    url = url.strip()
    url = url.rstrip(".,);]}>\"'")

    if not url.startswith("http"):
        url = "https://" + url

    return url


def extract_urls(text):
    if not text:
        return []

    pattern = r"(https?://[^\s<>\"]+|www\.[^\s<>\"]+)"
    matches = re.findall(pattern, text)

    urls = []

    for match in matches:
        url = clean_url(match)
        if url:
            urls.append(url)

    return list(dict.fromkeys(urls))


def remove_urls_from_text(text):
    if not text:
        return ""

    pattern = r"(https?://[^\s<>\"]+|www\.[^\s<>\"]+)"
    cleaned = re.sub(pattern, "", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned


def classify_source_type(url):
    if not url:
        return "text"

    lowered = url.lower()

    if "linkedin.com" in lowered:
        return "linkedin"
    if "twitter.com" in lowered or "x.com" in lowered:
        return "twitter"
    if "instagram.com" in lowered:
        return "instagram"
    if "youtube.com" in lowered or "youtu.be" in lowered:
        return "youtube"
    if "medium.com" in lowered:
        return "medium_article"
    if "substack.com" in lowered:
        return "substack_article"
    if "techcrunch.com" in lowered:
        return "techcrunch_article"
    if "ycombinator.com" in lowered:
        return "ycombinator"
    if any(host in lowered for host in ["blog.", "/article", "/news"]):
        return "article"

    return "website"


def fallback_source_name(url):
    if not url:
        return "Brainboard Note"

    lowered = url.lower()

    known_sources = {
        "linkedin.com": "LinkedIn",
        "twitter.com": "X",
        "x.com": "X",
        "instagram.com": "Instagram",
        "youtube.com": "YouTube",
        "youtu.be": "YouTube",
        "medium.com": "Medium",
        "substack.com": "Substack",
        "techcrunch.com": "TechCrunch",
        "ycombinator.com": "Y Combinator",
    }

    for domain, name in known_sources.items():
        if domain in lowered:
            return name

    clean = lowered.replace("https://", "").replace("http://", "").replace("www.", "")
    return clean.split("/")[0]


def fetch_url_content(url):
    if not url:
        return None

    normalized = url.replace("https://", "").replace("http://", "")
    jina_url = f"https://r.jina.ai/http://{normalized}"

    try:
        response = requests.get(
            jina_url,
            timeout=12,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        response.raise_for_status()

        text = response.text.strip()

        if text and len(text) > 30:
            return text[:12000]

    except Exception as e:
        print("Jina fetch failed:", e)

    try:
        response = requests.get(
            url,
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        response.raise_for_status()

        page_html = response.text or ""

        cleaned = re.sub(r"(?is)<script.*?>.*?</script>", " ", page_html)
        cleaned = re.sub(r"(?is)<style.*?>.*?</style>", " ", cleaned)
        cleaned = re.sub(r"(?s)<[^>]+>", " ", cleaned)
        cleaned = html_lib.unescape(re.sub(r"\s+", " ", cleaned)).strip()

        return cleaned[:12000]

    except Exception as e:
        print("Fallback scraper failed:", e)
        return None


def extract_linkedin_post_hint(url):
    if not url or "linkedin.com/posts/" not in url.lower():
        return None

    try:
        parsed = urlparse(url)
        path = parsed.path or ""
        slug = path.split("/posts/")[-1]

        if "_" in slug:
            slug = slug.split("_", 1)[1]

        slug = re.sub(r"-\d+[a-zA-Z]*$", "", slug)
        slug = re.sub(r"-share$", "", slug)

        text = unquote(slug).replace("-", " ").strip()
        text = re.sub(r"\b\d{8,}\b", " ", text)
        text = re.sub(r"\b[A-Z]{3,}\b$", " ", text)
        text = re.sub(r"\s+", " ", text).strip()

        if len(text) < 10:
            return None

        return f"LinkedIn post slug likely says: {text}"

    except Exception:
        return None


def parse_llm_json(content):
    content = (content or "").strip()

    if content.startswith("```json"):
        content = content.replace("```json", "").replace("```", "").strip()
    elif content.startswith("```"):
        content = content.replace("```", "").strip()

    return json.loads(content)


def analyze_with_llm(original_message, user_note="", url=None, scraped_text=None):
    if not client:
        raise RuntimeError("OPENAI_API_KEY is not configured.")

    scraped_text = scraped_text or ""
    user_note = user_note or ""

    prompt = f"""
You are Brainboard AI, a skillful personal note-making agent.

Your job is to convert messy WhatsApp inputs into clean, useful, searchable notes.

The user may send:
1. Only a text note
2. Only a link
3. A text note + a relevant link
4. A todo list / checklist / action items

You must combine:
- the user's own note
- the detected link
- the scraped content from the link

Original WhatsApp message:
{original_message}

User-written note after removing URLs:
{user_note}

Detected URL:
{url}

Scraped content from URL:
{scraped_text}

Important rules:
- If the user gave both a note and a link, combine both.
- The user's note is important context. Do not ignore it.
- If link content is available, summarize the actual content of the link.
- If scraped content is weak or unavailable, use the user's note and URL slug.
- Do not invent facts.
- Make the note useful for future reading.
- Write like a smart founder/product person taking notes.
- Keep it crisp and practical.
- Avoid generic lines like "This article discusses..."
- Return only valid JSON.

Important todo rule:
- If the message contains todos, tasks, checklist items, numbered lists, or action points, preserve every distinct todo.
- If the user sends 6 todos, return 6 bullet points.
- If the user sends 10 todos, return 10 bullet points.
- Do not compress multiple todos into only 3 points.
- Clean and rewrite each todo, but do not drop any.
- Only merge todos if they are clearly duplicates.
- For todos, category should be "Todo".
- For todos, source_type should be "text".
- For todos, source_name should be "Brainboard Note".

Create:
1. A short, clear title
2. A useful summary in bullet points
3. The user's context or reason for saving, if clear
4. A category
5. Source type
6. Source name
7. Suggested tags

Allowed categories:
Business, AI, Finance, Product, Growth, Startup, Hiring, Marketing, Personal Idea, Research, Todo, Other

Allowed source_type:
text, website, article, company_website, twitter, linkedin, instagram, youtube, medium_article, substack_article, techcrunch_article, ycombinator

Return JSON in this exact format:

{{
  "title": "short useful title",
  "summary": [
    "one bullet per important note, insight, or todo",
    "preserve all todos from the user",
    "do not compress multiple todos into one unless they are duplicates"
  ],
  "user_context": "why the user saved this, if clear",
  "category": "Todo",
  "source_type": "text",
  "source_name": "Brainboard Note",
  "tags": ["todo", "startup", "operations"]
}}
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        timeout=20,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )

    content = response.choices[0].message.content
    return parse_llm_json(content)


def send_whatsapp_message(to_number, from_number, body):
    if not twilio_client:
        print("Twilio message skipped: client not configured.")
        return

    try:
        twilio_client.messages.create(
            body=body,
            from_=from_number,
            to=to_number
        )
    except Exception as e:
        print("Twilio final message failed:", e)


def normalize_analysis(analysis, url, message):
    title = analysis.get("title") or (url or message).strip()[:70] or "Saved item"

    summary = analysis.get("summary", [])
    if isinstance(summary, list):
        summary_text = "\n".join(summary)
    else:
        summary_text = str(summary)

    return {
        "title": title,
        "summary": summary_text,
        "user_context": analysis.get("user_context"),
        "category": analysis.get("category") or "Other",
        "source_type": analysis.get("source_type") or classify_source_type(url),
        "source_name": analysis.get("source_name") or fallback_source_name(url),
        "tags": analysis.get("tags") if isinstance(analysis.get("tags"), list) else []
    }


def process_and_save_message(from_number, twilio_number, message):
    try:
        if not supabase:
            raise RuntimeError("Supabase not configured.")

        urls = extract_urls(message)
        user_note = remove_urls_from_text(message)
        items_to_process = urls if urls else [None]
        saved_titles = []

        for idx, url in enumerate(items_to_process):
            message_type = "link" if url else "note"

            scraped_text = fetch_url_content(url) if url else None

            if not scraped_text and classify_source_type(url) == "linkedin":
                scraped_text = extract_linkedin_post_hint(url)

            try:
                analysis = analyze_with_llm(
                    original_message=message,
                    user_note=user_note,
                    url=url,
                    scraped_text=scraped_text
                )

            except Exception as e:
                print(f"LLM analysis failed for item {idx + 1}:", e)

                fallback_title = (user_note or url or message).strip()[:70] or "Saved item"

                analysis = {
                    "title": fallback_title,
                    "summary": [
                        "Could not generate AI notes right now.",
                        "The original message or link has still been saved.",
                        "You can revisit it later in Brainboard."
                    ],
                    "user_context": user_note,
                    "category": "Other",
                    "source_type": classify_source_type(url),
                    "source_name": fallback_source_name(url),
                    "tags": []
                }

            note = normalize_analysis(analysis, url, message)

            try:
                supabase.table("brainboard_items").insert({
                    "whatsapp_number": from_number,
                    "original_message": message,
                    "message_type": message_type,
                    "url": url,
                    "title": note["title"],
                    "summary": note["summary"],
                    "user_context": note["user_context"],
                    "category": note["category"],
                    "source_type": note["source_type"],
                    "source_name": note["source_name"],
                    "tags": note["tags"],
                    "is_read": False
                }).execute()

                saved_titles.append(note["title"])
                print("Saved:", note["title"])

            except Exception as e:
                print(f"Supabase insert failed for item {idx + 1}:", e)

        if saved_titles:
            if len(saved_titles) == 1:
                confirmation_message = f"*{saved_titles[0]}* saved in Brainboard ✅"
                if len(confirmation_message) > 140:
                    confirmation_message = "Saved in Brainboard ✅"
            else:
                confirmation_message = f"Saved {len(saved_titles)} notes in Brainboard ✅"

            send_whatsapp_message(
                to_number=from_number,
                from_number=twilio_number,
                body=confirmation_message
            )
        else:
            send_whatsapp_message(
                to_number=from_number,
                from_number=twilio_number,
                body="I received it, but could not save it right now. Please try again."
            )

    except Exception as e:
        print("Background processing failed:", e)

        send_whatsapp_message(
            to_number=from_number,
            from_number=twilio_number,
            body="I received it, but something went wrong while saving."
        )


@app.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Request, background_tasks: BackgroundTasks):
    form = await request.form()

    from_number = form.get("From")
    twilio_number = form.get("To")
    message = form.get("Body") or ""

    background_tasks.add_task(
        process_and_save_message,
        from_number,
        twilio_number,
        message
    )

    twilio_response = MessagingResponse()
    twilio_response.message("Making notes for Brainboard...")

    return Response(
        content=str(twilio_response),
        media_type="application/xml"
    )