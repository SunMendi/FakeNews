import os
import logging
import json
import httpx
from google import genai
from google.genai import types
from groq import Groq
from django.conf import settings

logger = logging.getLogger(__name__)

class FailoverLLM:
    """
    Principal Architect Pattern: Resilient LLM Service.
    Tier 1: Gemini (Primary)
    Tier 2: Groq (High-speed Fallback)
    Tier 3: OpenRouter (Universal Fallback)
    """
    def __init__(self):
        # 1. Gemini Config
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        self.gemini_client = genai.Client(api_key=self.gemini_key) if self.gemini_key else None
        # ARCHITECTURAL FIX: Use valid model name 'gemini-2.0-flash'
        self.gemini_model = "gemini-2.0-flash"

        # 2. Groq Config
        self.groq_key = os.getenv("GROQ_API_KEY")
        self.groq_client = Groq(api_key=self.groq_key) if self.groq_key else None
        self.groq_model = "llama-3.3-70b-versatile"

        # 3. OpenRouter Config
        self.openrouter_key = os.getenv("OPENROUTER_API_KEY")
        self.openrouter_url = "https://openrouter.ai/api/v1/chat/completions"
        self.openrouter_model = "google/gemini-2.0-flash-001" 

    def generate(self, prompt: str, system_instruction: str = "", is_json: bool = False) -> str:
        """Execute generation with 3-tier failover."""
        
        # --- Tier 1: Gemini ---
        if self.gemini_client:
            try:
                response = self.gemini_client.models.generate_content(
                    model=self.gemini_model,
                    contents=f"{system_instruction}\n\n{prompt}" if system_instruction else prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.1,
                        max_output_tokens=500,
                        response_mime_type="application/json" if is_json else "text/plain"
                    )
                )
                if response.text:
                    return response.text.strip()
            except Exception as e:
                logger.error(f"LLM_ERROR Tier 1 (Gemini) failed: {e}")

        # --- Tier 2: Groq ---
        if self.groq_client:
            try:
                messages = []
                if system_instruction:
                    messages.append({"role": "system", "content": system_instruction})
                messages.append({"role": "user", "content": prompt})

                response = self.groq_client.chat.completions.create(
                    model=self.groq_model,
                    messages=messages,
                    temperature=0.1,
                    response_format={"type": "json_object"} if is_json else None
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                logger.error(f"LLM_ERROR Tier 2 (Groq) failed: {e}")

        # --- Tier 3: OpenRouter ---
        if self.openrouter_key:
            try:
                headers = {
                    "Authorization": f"Bearer {self.openrouter_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "http://localhost:8000",
                }
                messages = []
                if system_instruction:
                    messages.append({"role": "system", "content": system_instruction})
                messages.append({"role": "user", "content": prompt})

                payload = {
                    "model": self.openrouter_model,
                    "messages": messages,
                    "temperature": 0.1,
                }
                if is_json:
                    payload["response_format"] = {"type": "json_object"}

                with httpx.Client(timeout=15.0) as client:
                    resp = client.post(self.openrouter_url, headers=headers, json=payload)
                    resp.raise_for_status()
                    return resp.json()["choices"][0]["message"]["content"].strip()
            except Exception as e:
                logger.error(f"LLM_ERROR Tier 3 (OpenRouter) failed: {e}")

        logger.critical("LLM_CRITICAL_FAILURE: All providers failed.")
        return ""

# Singleton instance
llm = FailoverLLM()

# --- Specialized Functions ---

REFINER_PROMPT = """
You are a query normalization assistant. Extract the "Core Search Intent".
Rules:
1. Convert Banglish/Bengali to Standard English or Bengali.
2. Remove noise ("is this true?", "bolen to").
3. DO NOT truncate names or locations.
4. Output ONLY the refined query string.
"""

def refine_query(text: str) -> str:
    if not text.strip():
        return ""
    
    result = llm.generate(
        prompt=f"Input: {text}\nOutput:",
        system_instruction=REFINER_PROMPT
    )
    return result if result else text.strip()
