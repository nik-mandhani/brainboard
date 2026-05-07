


from fastapi import FastAPI, Request, Response
from supabase import create_client
from openai import OpenAI
from twilio.twiml.messaging_response import MessagingResponse
from dotenv import load_dotenv
import os
import re
import json
import html as html_lib
import requests

load_dotenv()

app = FastAPI()

SUPABASE_URL = "https://pmmtjnnhbursfwgkikzw.supabase.co"
SUPABASE_KEY = "sb_publishable_c96M4rB40pZR61acb-9KNg_9UC3uKd7"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

twilio_client = TwilioClient(
    os.getenv("TWILIO_ACCOUNT_SID"),
    os.getenv("TWILIO_AUTH_TOKEN")
)


@app.get("/")
def home():
    return {"status": "Brainboard server is running"}


def extract_url(text):
    pattern = r'((https?://)?(www\.)?[a-zA-Z0-9\-]+\.[a-zA-Z]{2,}(/\S*)?)'
    matches = re.findall(pattern, text or "")

    if not matches:
        return None

    url = matches[0][0]

    if not url.startswith("http"):
        url = "https://" + url

    return url


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


def parse_llm_json(content):
    content = content.strip()

    if content.startswith("```json"):
        content = content.replace("```json", "").replace("```", "").strip()
    elif content.startswith("```"):
        content = content.replace("```", "").strip()

    return json.loads(content)


def analyze_with_llm(message, url=None, scraped_text=None):
    scraped_text = scraped_text or ""

    prompt = f"""
You are Brainboard AI.

The user is saving a link or thought to their personal Brainboard.

User message:
{message}

Detected URL:
{url}

Scraped page text:
{scraped_text}

Create:
1. A clean single-line title
2. A useful 3-point summary
3. A category
4. A source type
5. A source name

Important:
- If scraped text contains tweet/post content, summarize the tweet/post itself.
- Do not invent details.
- Keep title short and human-readable.
- Let source_type be specific when obvious.
- If source is a known company/platform, put that in source_name.

Examples:
- X link → source_type=twitter, source_name=X
- LinkedIn link → source_type=linkedin, source_name=LinkedIn
- Medium → source_type=medium_article, source_name=Medium
- Plain text → source_type=text, source_name=Brainboard Note

Return ONLY valid JSON.

{{
  "title": "clean short title",
  "summary": [
    "point 1",
    "point 2",
    "point 3"
  ],
  "category": "Business / Politics / AI / Finance / Sports / Entertainment / Personal Idea / Other",
  "source_type": "twitter / linkedin / instagram / youtube / medium_article / substack_article / techcrunch_article / company_website / article / website / text",
  "source_name": "X / LinkedIn / Instagram / YouTube / Medium / Substack / TechCrunch / Y Combinator / company name / Brainboard Note"
}}
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        timeout=15,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )

    content = response.choices[0].message.content
    return parse_llm_json(content)


def send_whatsapp_message(to_number, from_number, body):
    try:
        twilio_client.messages.create(
            body=body,
            from_=from_number,
            to=to_number
        )
    except Exception as e:
        print("Twilio final message failed:", e)


def process_and_save_message(from_number, twilio_number, message):
    try:
        url = extract_url(message)
        message_type = "link" if url else "note"

        scraped_text = fetch_url_content(url) if url else None

        try:
            analysis = analyze_with_llm(
                message=message,
                url=url,
                scraped_text=scraped_text
            )
        except Exception as e:
            print("LLM analysis failed:", e)

            fallback_title = message.strip()[:70] or "Saved item"

            analysis = {
                "title": fallback_title,
                "summary": [
                    "Could not generate AI summary right now.",
                    "The original message or link has still been saved.",
                    "You can revisit it later in Brainboard."
                ],
                "category": "Other",
                "source_type": classify_source_type(url),
                "source_name": fallback_source_name(url)
            }

        title = analysis.get("title", "Saved item")
        summary = "\n".join(analysis.get("summary", []))
        category = analysis.get("category", "Other")
        source_type = analysis.get("source_type") or classify_source_type(url)
        source_name = analysis.get("source_name") or fallback_source_name(url)

        try:
            supabase.table("brainboard_items").insert({
                "whatsapp_number": from_number,
                "original_message": message,
                "message_type": message_type,
                "url": url,
                "title": title,
                "summary": summary,
                "category": category,
                "source_type": source_type,
                "source_name": source_name
            }).execute()

            print("Saved:", title)

            confirmation_message = f"*{title}* saved in Brainboard ✅"

            if len(confirmation_message) > 140:
                confirmation_message = "Saved in Brainboard ✅"

            send_whatsapp_message(
                to_number=from_number,
                from_number=twilio_number,
                body=confirmation_message
            )

        except Exception as e:
            print("Supabase insert failed:", e)

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
    twilio_response.message("Saving to Brainboard...")

    return Response(
        content=str(twilio_response),
        media_type="application/xml"
    )