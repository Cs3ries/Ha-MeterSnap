"""Vision AI OCR Engine for MeterSnap."""
from __future__ import annotations

import base64
import json
import logging
import re
from typing import Any

import aiohttp

from .const import (
    DEFAULT_CUSTOM_MODEL,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_OPENAI_MODEL,
    METER_ELECTRICITY,
    METER_GAS,
    PROVIDER_CUSTOM,
    PROVIDER_GEMINI,
    PROVIDER_OPENAI,
)

_LOGGER = logging.getLogger(__name__)


def build_ocr_prompt(meter_type: str) -> str:
    """Build a specialized prompt for meter reading extraction."""
    type_desc = "Stromzähler" if meter_type == METER_ELECTRICITY else "Gaszähler"
    unit = "kWh" if meter_type == METER_ELECTRICITY else "m³"

    return f"""Du bist ein präziser Experte für das Auslesen von Zählerständen ({type_desc}).
Analysiere das beigefügte Foto und ermittle den exakten aktuellen Zählerstand.

Regeln:
1. Zählertyp ist: {type_desc} (Einheit: {unit}).
2. Wenn Stromzähler:
   - Bei analogen Ferraris-Zählern: Schwarze Ziffernrollen sind ganze Zahlen vor dem Komma. Eine rote Rolle ganz rechts ist die Nachkommastelle (z.B. 12345.6). Falls keine rote Rolle existiert, gibt es keine Nachkommastellen.
   - Bei digitalen Zählern (LCD/mME): Suche gezielt nach dem Kenncode '1.8.0' (Bezug/Verbrauch). Ignoriere '2.8.0' (Einspeisung) und Prüfanzeigen (wie 888888).
3. Wenn Gaszähler:
   - Ziffernrollen mit schwarzem Hintergrund sind ganze m³.
   - Ziffernrollen mit rotem Rahmen / rotem Hintergrund (meist 3 Ziffern ganz rechts) sind Nachkommastellen (z.B. 04285.391 m³).
4. Ignoriere Barcodes, Eigentumsnummern, Seriennummern, Zählernummern, Baujahr und Warnhinweise.
5. Gib das Ergebnis AUSSCHLIESSLICH als valides JSON-Objekt ohne Erklärungen und ohne Markdown-Code-Ticks zurück.

Format:
{{
  "reading": 12345.67,
  "integer_part": 12345,
  "decimal_part": 67,
  "unit": "{unit}",
  "confidence": "high",
  "details": "Erkannt von Zählwerk..."
}}"""


def clean_json_response(raw_text: str) -> dict[str, Any] | None:
    """Extract and parse JSON from model response with fallback strategies."""
    if not raw_text:
        return None

    cleaned = raw_text.strip()

    # 1. Remove <think>...</think> reasoning blocks from thinking models (e.g. Ling, DeepSeek, Qwen)
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()

    # 2. Extract from markdown code blocks ```json ... ``` or ``` ... ```
    code_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if code_block:
        candidate = code_block.group(1).strip()
        try:
            data = json.loads(candidate)
            if isinstance(data, dict) and "reading" in data:
                data["reading"] = float(data["reading"])
                return data
        except Exception:
            pass

    # 3. Non-greedy search for JSON object with "reading"
    json_match = re.search(r"(\{[^{}]*\"reading\"[^{}]*\})", cleaned, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            if isinstance(data, dict) and "reading" in data:
                data["reading"] = float(data["reading"])
                return data
        except Exception:
            pass

    # 4. Greedy search fallback
    json_greedy = re.search(r"(\{.*\})", cleaned, re.DOTALL)
    if json_greedy:
        try:
            data = json.loads(json_greedy.group(1))
            if isinstance(data, dict) and "reading" in data:
                data["reading"] = float(data["reading"])
                return data
        except Exception:
            pass

    # 5. Regex extraction fallback (e.g. "reading": 47843.2)
    reading_match = re.search(r'["\']?reading["\']?\s*[:=]\s*["\']?([0-9]+(?:[\.,][0-9]+)?)["\']?', cleaned, re.IGNORECASE)
    if reading_match:
        val_str = reading_match.group(1).replace(",", ".")
        try:
            return {
                "reading": float(val_str),
                "confidence": "medium",
                "details": "Per Fallback-Muster aus KI-Antwort extrahiert",
            }
        except (ValueError, TypeError):
            pass

    # 6. Fallback: search for numbers after German keywords like "Zählerstand ... 47843.2"
    keyword_match = re.search(r'(?:zählerstand|stand|verbrauch|wert|reading).*?([0-9]{3,7}(?:[\.,][0-9]+)?)', cleaned, re.IGNORECASE)
    if keyword_match:
        val_str = keyword_match.group(1).replace(",", ".")
        try:
            return {
                "reading": float(val_str),
                "confidence": "medium",
                "details": "Aus Textantwort extrahiert",
            }
        except (ValueError, TypeError):
            pass

    # 7. Last-resort fallback: extract any 4-7 digit number with optional decimals
    number_match = re.search(r'\b([0-9]{4,7}(?:[\.,][0-9]+)?)\s*(?:kwh|m³|m3)?\b', cleaned, re.IGNORECASE)
    if number_match:
        val_str = number_match.group(1).replace(",", ".")
        try:
            return {
                "reading": float(val_str),
                "confidence": "low",
                "details": "Zahlenmuster erkannt",
            }
        except (ValueError, TypeError):
            pass

    _LOGGER.warning("Could not parse meter reading from OCR response: %s", raw_text)
    return None


class MeterSnapOCREngine:
    """OCR Engine handling Vision AI requests."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        provider: str = PROVIDER_GEMINI,
        api_key: str = "",
        custom_endpoint: str = "",
        custom_model: str = "",
    ) -> None:
        self._session = session
        self._provider = provider
        self._api_key = api_key
        self._custom_endpoint = custom_endpoint
        self._custom_model = custom_model

    async def scan_image(
        self,
        image_bytes: bytes,
        meter_type: str = METER_ELECTRICITY,
        mime_type: str = "image/jpeg",
    ) -> dict[str, Any]:
        """Send image to selected AI provider and extract meter reading."""
        prompt = build_ocr_prompt(meter_type)

        try:
            if self._provider == PROVIDER_GEMINI:
                return await self._scan_gemini(image_bytes, prompt, mime_type)
            elif self._provider == PROVIDER_OPENAI:
                return await self._scan_openai(image_bytes, prompt, mime_type)
            elif self._provider == PROVIDER_CUSTOM:
                return await self._scan_custom(image_bytes, prompt, mime_type)
            else:
                return {
                    "success": False,
                    "error": f"Unbekannter OCR Provider: {self._provider}",
                }
        except Exception as err:
            _LOGGER.exception("Error during meter OCR scan: %s", err)
            return {"success": False, "error": str(err)}

    async def _scan_gemini(
        self,
        image_bytes: bytes,
        prompt: str,
        mime_type: str,
    ) -> dict[str, Any]:
        """Call Google Gemini API."""
        if not self._api_key:
            return {"success": False, "error": "Kein Google Gemini API-Schlüssel hinterlegt."}

        model = DEFAULT_GEMINI_MODEL
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            f"?key={self._api_key}"
        )

        b64_data = base64.b64encode(image_bytes).decode("utf-8")
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": b64_data,
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "response_mime_type": "application/json",
            },
        }

        async with self._session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=45)) as resp:
            if resp.status != 200:
                text = await resp.text()
                return {
                    "success": False,
                    "error": f"Gemini API Fehler ({resp.status}): {text[:200]}",
                }

            result_json = await resp.json()
            candidates = result_json.get("candidates", [])
            if not candidates:
                return {"success": False, "error": "Gemini lieferte keine Antwort."}

            part = candidates[0].get("content", {}).get("parts", [{}])[0]
            raw_text = part.get("text", "")

            parsed = clean_json_response(raw_text)
            if parsed:
                parsed["success"] = True
                return parsed

            return {
                "success": False,
                "error": "Antwort konnte nicht als Zählerstand geparst werden.",
                "raw": raw_text,
            }

    async def _scan_openai(
        self,
        image_bytes: bytes,
        prompt: str,
        mime_type: str,
    ) -> dict[str, Any]:
        """Call OpenAI Vision API."""
        if not self._api_key:
            return {"success": False, "error": "Kein OpenAI API-Schlüssel hinterlegt."}

        url = "https://api.openai.com/v1/chat/completions"
        b64_data = base64.b64encode(image_bytes).decode("utf-8")
        data_uri = f"data:{mime_type};base64,{b64_data}"

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": DEFAULT_OPENAI_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_uri, "detail": "high"}},
                    ],
                }
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }

        async with self._session.post(
            url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=45)
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                return {
                    "success": False,
                    "error": f"OpenAI API Fehler ({resp.status}): {text[:200]}",
                }

            result_json = await resp.json()
            choices = result_json.get("choices", [])
            if not choices:
                return {"success": False, "error": "OpenAI lieferte keine Antwort."}

            raw_text = choices[0].get("message", {}).get("content", "")
            parsed = clean_json_response(raw_text)
            if parsed:
                parsed["success"] = True
                return parsed

            return {
                "success": False,
                "error": "Antwort konnte nicht als Zählerstand geparst werden.",
                "raw": raw_text,
            }

    async def _scan_custom(
        self,
        image_bytes: bytes,
        prompt: str,
        mime_type: str,
    ) -> dict[str, Any]:
        """Call Custom / Local OpenAI-compatible Vision API."""
        url = self._custom_endpoint or "http://localhost:11434/v1/chat/completions"
        model = self._custom_model or DEFAULT_CUSTOM_MODEL
        b64_data = base64.b64encode(image_bytes).decode("utf-8")
        data_uri = f"data:{mime_type};base64,{b64_data}"

        headers = {
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/Cs3ries/Ha-MeterSnap",
            "X-Title": "MeterSnap",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": data_uri, "detail": "auto"},
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            "temperature": 0.1,
            "max_tokens": 2048,
            "reasoning": {"exclude": True},
        }

        async with self._session.post(
            url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=60)
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                _LOGGER.error("Custom API error response (%s): %s", resp.status, text)
                error_msg = text
                try:
                    err_json = json.loads(text)
                    if isinstance(err_json, dict) and "error" in err_json:
                        err_info = err_json["error"]
                        if isinstance(err_info, dict):
                            msg = err_info.get("message", "")
                            meta = err_info.get("metadata", {})
                            if isinstance(meta, dict) and "raw" in meta:
                                raw_str = meta["raw"]
                                try:
                                    raw_json = json.loads(raw_str)
                                    if isinstance(raw_json, dict) and "message" in raw_json:
                                        msg = f"{msg} ({raw_json['message']})"
                                except Exception:
                                    msg = f"{msg} ({raw_str[:150]})"
                            error_msg = msg or str(err_info)
                        else:
                            error_msg = str(err_info)
                except Exception:
                    pass
                return {
                    "success": False,
                    "error": f"Custom API Fehler ({resp.status}): {error_msg[:300]}",
                }

            result_json = await resp.json()
            choices = result_json.get("choices", [])
            if not choices:
                return {"success": False, "error": "Custom API lieferte keine Antwort."}

            raw_text = choices[0].get("message", {}).get("content", "")
            parsed = clean_json_response(raw_text)
            if parsed:
                parsed["success"] = True
                return parsed

            return {
                "success": False,
                "error": "Antwort konnte nicht als Zählerstand geparst werden.",
                "raw": raw_text,
            }
