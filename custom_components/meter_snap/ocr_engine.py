"""Vision AI OCR Engine for MeterSnap."""
from __future__ import annotations

import asyncio
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
   - Bei analogen Ferraris-Zählern: Schwarze Ziffernrollen sind ganze Zahlen vor dem Komma. Eine rote Rolle ganz rechts ist die Nachkommastelle (z.B. 12345 auf Schwarz und 6 auf Rot ergibt 12345.6 kWh). Falls keine rote Rolle existiert, gibt es keine Nachkommastellen.
   - Bei digitalen Zählern (LCD/mME): Suche gezielt nach dem Kenncode '1.8.0' (Bezug/Verbrauch). Ignoriere '2.8.0' (Einspeisung) und Prüfanzeigen (wie 888888).
3. Wenn Gaszähler:
   - Ziffernrollen mit schwarzem Hintergrund sind ganze m³. Führende Nullen bei ganzen Zahlen weglassen oder beibehalten.
   - Ziffernrollen mit rotem Rahmen / rotem Hintergrund (meist 3 Ziffern ganz rechts) sind Nachkommastellen (z.B. 01234 im schwarzen Bereich und 567 im roten Bereich ergibt 1234.567 m³).
4. Ignoriere Barcodes, Eigentumsnummern, Seriennummern, Zählernummern, Baujahr und Warnhinweise (z.B. Seriennummern oder Herstellerangaben wie Landis+Gyr, Itron etc. ignorieren).
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


def parse_number_str(val: Any) -> float | None:
    """Parse string or number into float supporting German and English notation."""
    if val is None:
        return None
    s = str(val).strip()
    # Strip leading OBIS code if present (e.g. 1.8.0: or 1.8.0*00)
    s = re.sub(r"^(?:1-0:)?(?:[0-2]\.8\.[0-9](?:\*\d+)?)[\s:=*]+", "", s).strip()
    s = s.replace(" ", "")
    s = re.sub(r"[kwhm³m3]+$", "", s, flags=re.IGNORECASE).strip()
    # If both dot and comma exist: e.g. 47.843,2 (German) or 47,843.2 (English)
    if "." in s and "," in s:
        if s.rfind(",") > s.rfind("."):  # German 47.843,2
            s = s.replace(".", "").replace(",", ".")
        else:  # English 47,843.2
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def clean_json_response(raw_text: str) -> dict[str, Any] | None:
    """Extract and parse JSON from model response with fallback strategies."""
    if not raw_text:
        return None

    cleaned = raw_text.strip()

    # 1. Remove <think>...</think> reasoning blocks from thinking models (e.g. Ling, DeepSeek, Qwen)
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()

    candidates = []

    # 2. Extract from markdown code blocks ```json ... ``` or ``` ... ```
    code_blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    candidates.extend(code_blocks)

    # 3. Non-greedy search for JSON objects with "reading" or "integer_part"
    json_matches = re.findall(r"(\{[^{}]*(?:\"reading\"|\"integer_part\")[^{}]*\})", cleaned, re.DOTALL)
    candidates.extend(json_matches)

    # 4. Greedy search fallback
    json_greedy = re.findall(r"(\{.*\})", cleaned, re.DOTALL)
    candidates.extend(json_greedy)

    candidates.append(cleaned)

    for cand in candidates:
        cand_clean = cand.strip()
        # Remove trailing commas before } or ]
        cand_clean = re.sub(r",\s*([\}\]])", r"\1", cand_clean)
        try:
            data = json.loads(cand_clean)
            if isinstance(data, dict):
                if "reading" in data and data["reading"] is not None:
                    num = parse_number_str(data["reading"])
                    if num is not None:
                        data["reading"] = num
                        return data
                if "integer_part" in data and data["integer_part"] is not None:
                    int_str = str(data["integer_part"]).strip().replace(" ", "")
                    dec_str = str(data.get("decimal_part", "")).strip().replace(" ", "")
                    full_str = f"{int_str}.{dec_str}" if dec_str and dec_str != "0" else int_str
                    num = parse_number_str(full_str)
                    if num is not None:
                        data["reading"] = num
                        return data
        except Exception:
            pass

    # 5. Roll description match (e.g. "schwarz: 047843, rot: 2")
    roll_match = re.search(r'(?:schwarz|vorkomma).*?([0-9]{3,7}).*?(?:rot|nachkomma).*?([0-9]{1,3})', cleaned, re.IGNORECASE)
    if roll_match:
        num = parse_number_str(f"{roll_match.group(1)}.{roll_match.group(2)}")
        if num is not None:
            return {"reading": num, "confidence": "high", "details": "Aus Rollenbeschreibung erkannt"}

    # 5b. Match OBIS 1.8.0 code for digital electricity meters
    obis_match = re.search(r'(?:1\.8\.0|1-0:1\.8\.0)[\s:=*]+([0-9][0-9\.,\s]{1,10}[0-9])', cleaned, re.IGNORECASE)
    if obis_match:
        num = parse_number_str(obis_match.group(1))
        if num is not None:
            return {"reading": num, "confidence": "high", "details": "Aus OBIS 1.8.0 Kennziffer erkannt"}

    # 6. Regex extraction fallback for "reading": ...
    reading_match = re.search(r'["\']?reading["\']?\s*[:=]\s*["\']?([0-9][0-9\.,\s]*[0-9])["\']?', cleaned, re.IGNORECASE)
    if reading_match:
        num = parse_number_str(reading_match.group(1))
        if num is not None:
            return {
                "reading": num,
                "confidence": "medium",
                "details": "Per Fallback-Muster aus KI-Antwort extrahiert",
            }

    # 7. Fallback: search for numbers after German keywords like "Zählerstand ... 47.843,2"
    keyword_match = re.search(r'(?:zählerstand|stand|verbrauch|wert|reading).*?([0-9][0-9\.,\s]{2,10}[0-9])', cleaned, re.IGNORECASE)
    if keyword_match:
        num = parse_number_str(keyword_match.group(1))
        if num is not None:
            return {
                "reading": num,
                "confidence": "medium",
                "details": "Aus Textantwort extrahiert",
            }

    # 8. Last-resort fallback: extract any 3-7 digit number (strip OBIS codes first so 1.8.0 is not picked)
    cleaned_for_num = re.sub(r'\b[0-2]\.8\.[0-9]\b', '', cleaned)
    number_match = re.search(r'\b([0-9]{1,3}(?:[\.,\s][0-9]{3})*(?:[\.,][0-9]+)?|[0-9]{3,7}(?:[\.,][0-9]+)?)\s*(?:kwh|m³|m3)?\b', cleaned_for_num, re.IGNORECASE)
    if number_match:
        num = parse_number_str(number_match.group(1))
        if num is not None:
            return {
                "reading": num,
                "confidence": "low",
                "details": "Zahlenmuster erkannt",
            }

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

            snippet = (raw_text[:120] + "...") if len(raw_text) > 120 else raw_text
            return {
                "success": False,
                "error": f"Antwort konnte nicht als Zählerstand geparst werden (KI-Rückgabe: {snippet!r}).",
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

            snippet = (raw_text[:120] + "...") if len(raw_text) > 120 else raw_text
            return {
                "success": False,
                "error": f"Antwort konnte nicht als Zählerstand geparst werden (KI-Rückgabe: {snippet!r}).",
                "raw": raw_text,
            }

    async def _scan_custom(
        self,
        image_bytes: bytes,
        prompt: str,
        mime_type: str,
    ) -> dict[str, Any]:
        """Call Custom / Local OpenAI-compatible Vision API."""
        url = (self._custom_endpoint or "http://localhost:11434/v1/chat/completions").strip()
        if "openroueter.ai" in url:
            url = url.replace("openroueter.ai", "openrouter.ai")

        model = (self._custom_model or DEFAULT_CUSTOM_MODEL).strip()
        if "openroueter" in model:
            model = model.replace("openroueter", "openrouter")

        safe_mime = mime_type if mime_type in ("image/jpeg", "image/png", "image/webp") else "image/jpeg"
        b64_data = base64.b64encode(image_bytes).decode("utf-8")
        data_uri = f"data:{safe_mime};base64,{b64_data}"

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
            "max_tokens": 1024,
        }

        last_error = None
        for attempt in range(2):
            try:
                async with self._session.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=60, connect=15),
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

                    snippet = (raw_text[:120] + "...") if len(raw_text) > 120 else raw_text
                    return {
                        "success": False,
                        "error": f"Antwort konnte nicht als Zählerstand geparst werden (KI-Rückgabe: {snippet!r}).",
                        "raw": raw_text,
                    }
            except (aiohttp.ClientError, asyncio.TimeoutError) as net_err:
                last_error = net_err
                if attempt == 0:
                    _LOGGER.warning(
                        "Netzwerk-/DNS-Fehler beim Aufruf von %s (Versuch 1/2), erneuter Versuch in 1.5s: %s",
                        url,
                        net_err,
                    )
                    await asyncio.sleep(1.5)
                    continue

        return {
            "success": False,
            "error": f"Verbindungs-/DNS-Fehler zu {url}: {last_error}",
        }
