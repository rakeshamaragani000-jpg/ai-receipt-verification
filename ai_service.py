import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()


def generate_ai_response(prompt: str) -> str:
    """Generate an AI response, using a real OpenAI API if configured or a local fallback.

    This function intentionally avoids hard dependency on an external API so the project can
    be demonstrated locally without secret configuration.
    """
    api_key = os.getenv("OPENAI_API_KEY")

    if api_key:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key)
            completion = client.responses.create(
                model="gpt-4o-mini",
                input=[{"role": "user", "content": prompt}],
            )
            content = completion.output_text
            if content:
                return content
        except Exception:
            pass

    # Safe deterministic fallback for local demos and tests.
    return (
        f"Local fallback response for: '{prompt}'. "
        "This is a deterministic mock AI answer used when no external API key is configured."
    )
