"""Deterministic domain safety checks for requests and generated responses."""

from __future__ import annotations

import re

from agentkernel.core import (
    Agent,
    AgentReply,
    AgentReplyText,
    AgentRequest,
    AgentRequestText,
    PostHook,
    PreHook,
    Session,
)

from farmer_profile import normalized as _normalized
from language import clean_sinhala_weather_reply, session_reply_in_sinhala
from routing import Intent, classify_intent
from trusted_context import extract_original_message

AGROCHEMICAL_PRODUCT_TERMS = (
    "confidor",
    "imidacloprid",
    "කොන්ෆිඩෝර්",
)
# Every banned product name is also a chemical term, so the generic list is composed from it.
CHEMICAL_TERMS = AGROCHEMICAL_PRODUCT_TERMS + (
    "pesticide",
    "insecticide",
    "fungicide",
    "herbicide",
    "agrochemical",
    "chemical spray",
    "පළිබෝධනාශක",
    "කෘමිනාශක",
    "දිලීරනාශක",
    "වල්නාශක",
    "බෙහෙත් ඉස්",
)
SPRAY_APPLICATION_TERMS = (
    "spray",
    "ඉසි",
    "ඉස්",
)
PLAIN_WATER_TERMS = (
    "plain water",
    "spray water",
    "water spray",
    "වතුර",
)
DOSAGE_TERMS = (
    "dose",
    "dosage",
    "how much",
    "mixing ratio",
    "concentration",
    "per litre",
    "per liter",
    "tank",
    "interval",
    "මාත්‍රාව",
    "කොච්චර",
    "මිශ්‍ර කරන්න",
    "සීසී",
    "ටැංකිය",
    "ලීටර්",
    "ලීටර",
    "කීයක්",
)
EXPOSURE_TERMS = (
    "poison",
    "poisoning",
    "swallowed pesticide",
    "drank pesticide",
    "chemical exposure",
    "inhaled chemical",
    "chemical in my eyes",
    "skin burn",
    "animal is sick",
    "cannot breathe",
    "can't breathe",
    "difficulty breathing",
    "vomiting",
    "after spraying",
    "විෂ",
    "විෂ වීම",
    "බෙහෙත් බීවා",
    "ඇසට ගියා",
    "හුස්ම ගන්න අමාරුයි",
    "හුස්ම ගන්න බැහැ",
    "වමනය",
    "බෙහෙත් ඉස්සාට පස්සේ",
)
EXPOSURE_ACTION_TERMS = (
    "swallow",
    "swallowed",
    "drink",
    "drank",
    "ingested",
    "inhaled",
    "breathed in",
    "splashed",
    "in my eye",
    "in the eye",
    "on my skin",
    "dizzy",
    "dizziness",
    "unconscious",
    "බිව්වා",
    "බීවා",
    "ගිල",
    "ආශ්වාස",
    "ඇසට",
    "සමට",
    "කරකැවිල්ල",
    "සිහි නැති",
)
FINANCIAL_DECISION_TERMS = (
    "should i sell",
    "should i buy",
    "should i take a loan",
    "should i borrow",
    "guaranteed profit",
    "විකුණන්නද",
    "ණයක් ගන්නද",
    "ණය ගන්නද",
)

ENGLISH_AMOUNT_UNIT = r"(?:ml|cc|l|lit(?:er|re)|millilit(?:er|re)|g|gram|kg|tsp|tbsp)"
SINHALA_AMOUNT_UNIT = r"(?:මිලිලීටර්|සීසී|ලීටර්|ග්‍රෑම්|කිලෝග්‍රෑම්|තේ හැඳි|මේස හැඳි|%)"
SINHALA_ACTION = r"(?:මිශ්‍ර|යොද|ඉසි|දාන්න|දමන්න)"
SINHALA_AMOUNT = (
    rf"(?:\d+(?:\.\d+)?\s*(?:ක්\s*)?{SINHALA_AMOUNT_UNIT}|" rf"{SINHALA_AMOUNT_UNIT}\s*\d+(?:\.\d+)?(?:ක්)?)"
)
ENGLISH_AMOUNT = rf"\b\d+(?:\.\d+)?\s*(?:(?:{ENGLISH_AMOUNT_UNIT})\b|%)"

NUMERIC_CHEMICAL_PATTERN = re.compile(
    rf"(?:{ENGLISH_AMOUNT}|{SINHALA_AMOUNT})",
    re.IGNORECASE,
)
PRESCRIPTIVE_AMOUNT_PATTERN = re.compile(
    rf"(?:\b(?:mix|apply|spray|put|add|use)\b.{{0,50}}{ENGLISH_AMOUNT}|"
    rf"{SINHALA_ACTION}.{{0,50}}{SINHALA_AMOUNT}|"
    rf"{SINHALA_AMOUNT}.{{0,50}}{SINHALA_ACTION})",
    re.IGNORECASE,
)
PRESCRIPTIVE_PRODUCT_PATTERN = re.compile(
    r"(?:\b(?:use|apply|spray|mix)\s+[a-z][a-z0-9_-]{2,}\s+"
    r"(?:pesticide|insecticide|fungicide|herbicide)\b|"
    r"[a-z0-9_-]{2,}\s+(?:පළිබෝධනාශකය|කෘමිනාශකය|දිලීරනාශකය|වල්නාශකය)\s+"
    r"(?:භාවිතා කරන්න|යොදන්න|ඉසින්න|මිශ්‍ර කරන්න))",
    re.IGNORECASE,
)
# Short dosage abbreviations use explicit matchers instead of participating in substring matching.
# Keeping them out of DOSAGE_TERMS makes it impossible for a spelling change to silently discard
# the boundary policy and revive matches inside words such as "according" or "success".
BOUNDED_DOSAGE_PATTERNS = (re.compile(r"(?<!\w)cc(?!\w)"),)

NUMERIC_INFORMATION_PATTERN = re.compile(r"\d")
SOURCE_PATTERN = re.compile(r"(?:\bsource\b|මූලාශ්‍රය|මූලාශ්‍ර)", re.IGNORECASE)
DATE_PATTERN = re.compile(
    r"(?:\b\d{4}-\d{2}-\d{2}\b|\b\d{4}\.\d{2}\.\d{2}\b|"
    r"\b(?:as[- ]of|updated|data date|date)\b|දත්ත දිනය|යාවත්කාලීන)",
    re.IGNORECASE,
)
DEFINITIVE_DIAGNOSIS_PATTERN = re.compile(
    r"(?:\b(?:definitely|certainly|confirmed|without doubt)\b.{0,60}"
    r"(?:disease|virus|blight|wilt|anthracnose|blast)|"
    r"\bthis is\s+(?:leaf curl virus|anthracnose|bacterial wilt|rice blast|bacterial blight)\b|"
    r"(?:නිසැකවම|අනිවාර්යයෙන්ම|තහවුරුයි).{0,60}(?:රෝගය|වෛරසය|මැලවීම|අංගමාරය))",
    re.IGNORECASE,
)
UNQUALIFIED_DIAGNOSIS_PATTERN = re.compile(
    r"(?:\b(?:your|the)\b.{0,50}\b(?:has|have|is|suffers? from)\b.{0,40}"
    r"(?:leaf curl virus|anthracnose|bacterial wilt|rice blast|bacterial blight)|"
    r"\bthis is\b.{0,40}(?:leaf curl virus|anthracnose|bacterial wilt|rice blast|bacterial blight)|"
    r"(?:මෙය|මේක|ඔබගේ|ඔයාගේ).{0,60}(?:leaf curl virus|anthracnose|bacterial wilt|rice blast|"
    r"bacterial blight|රෝගයයි|වෛරසයයි|මැලවීමයි|අංගමාරයයි))",
    re.IGNORECASE,
)
FINANCIAL_REQUEST_PATTERN = re.compile(
    r"(?:\b(?:should|shall|can)\s+(?:i|we)\s+(?:sell|buy|borrow|take (?:a )?loan)\b|"
    r"\b(?:good|best) time to (?:sell|buy|borrow)\b|"
    r"(?:දැන්|අද).{0,20}(?:විකුණන්නද|මිලදී ගන්නද|ණය ගන්නද))",
    re.IGNORECASE,
)
FINANCIAL_DIRECTIVE_PATTERN = re.compile(
    r"(?:\b(?:you should|you must|i recommend(?: that you)?)\b.{0,50}"
    r"(?:sell|buy|borrow|take (?:a )?loan)\b|"
    r"\b(?:sell|buy|borrow)\b.{0,50}\b(?:now|today|immediately|best profit|guaranteed profit)\b|"
    r"(?:දැන්|අද|වහාම).{0,30}(?:විකුණන්න|මිලදී ගන්න|ණය ගන්න)|"
    r"(?:විකුණන්න|මිලදී ගන්න|ණය ගන්න).{0,30}(?:හොඳම|ලාභ))",
    re.IGNORECASE,
)


def _raw_text_from_requests(requests: list[AgentRequest]) -> str:
    return "\n".join(request.prompt for request in requests if isinstance(request, AgentRequestText))


def _original_text_from_requests(requests: list[AgentRequest]) -> str:
    return "\n".join(
        extract_original_message(request.prompt) for request in requests if isinstance(request, AgentRequestText)
    )


def _contains_any(normalized: str, terms: tuple[str, ...]) -> bool:
    """Test _normalized() output against a term tuple."""
    return any(term in normalized for term in terms)


def _has_dosage_context(normalized: str) -> bool:
    """Recognize dosage language without matching short abbreviations inside ordinary words."""
    return _contains_any(normalized, DOSAGE_TERMS) or any(
        pattern.search(normalized) for pattern in BOUNDED_DOSAGE_PATTERNS
    )


def _is_unsafe_amount_instruction(text: str, normalized: str) -> bool:
    """Identify chemical amounts while allowing clearly non-chemical cultural guidance."""
    chemical_context = _contains_any(normalized, CHEMICAL_TERMS)
    dosage_context = _has_dosage_context(normalized)
    spray_context = _contains_any(normalized, SPRAY_APPLICATION_TERMS)
    plain_water_only = _contains_any(normalized, PLAIN_WATER_TERMS) and not chemical_context
    numeric_amount = bool(NUMERIC_CHEMICAL_PATTERN.search(text))
    prescriptive_amount = bool(PRESCRIPTIVE_AMOUNT_PATTERN.search(text))

    return (
        (chemical_context and (dosage_context or numeric_amount or prescriptive_amount))
        or (dosage_context and prescriptive_amount)
        or (spray_context and (numeric_amount or (dosage_context and not plain_water_only)))
    )


def _is_chemical_exposure(normalized: str) -> bool:
    """Recognize emergency exposure phrasing independently from one exact chemical noun."""
    return _contains_any(normalized, EXPOSURE_TERMS) or (
        _contains_any(normalized, CHEMICAL_TERMS) and _contains_any(normalized, EXPOSURE_ACTION_TERMS)
    )


def chemical_referral(sinhala: bool) -> str:
    """Return the safe chemical-treatment boundary in the user's language."""
    if sinhala:
        return (
            "මට පළිබෝධනාශක නාම, මාත්‍රා, සාන්ද්‍රණ හෝ මිශ්‍ර කිරීමේ උපදෙස් ලබා දිය නොහැක. "
            "ලේබලය අනුගමනය කර ඔබගේ කෘෂිකර්ම උපදේශක හෝ ගොවිජන සේවා මධ්‍යස්ථානයෙන් උපදෙස් ගන්න."
        )
    return (
        "I can't provide agrochemical product names, dosages, concentrations, or mixing instructions. "
        "Follow the product label and ask an agricultural instructor or Agrarian Services Centre."
    )


def exposure_referral(sinhala: bool) -> str:
    """Return an immediate human/animal exposure referral."""
    if sinhala:
        return (
            "මෙය හදිසි සෞඛ්‍ය හෝ පශු වෛද්‍ය තත්ත්වයක් විය හැක. මෙම චැට් එකෙන් ප්‍රතිකාර නොකර "
            "වහාම සුදුසු හදිසි වෛද්‍ය හෝ පශු වෛද්‍ය සේවාව අමතන්න. භාවිත කළ ද්‍රව්‍යයේ ලේබලය "
            "හෝ බහාලුම ඔබ සමඟ රැගෙන යන්න."
        )
    return (
        "This may be a medical or veterinary emergency. Do not rely on this farming chat for treatment; "
        "contact appropriate emergency medical or veterinary help now and keep the product label or container available."
    )


def financial_boundary(sinhala: bool) -> str:
    """Return the informational-only market-price boundary."""
    if sinhala:
        return (
            "මට ඔබ වෙනුවෙන් විකිණීම, මිලදී ගැනීම හෝ ණය ගැනීම තීරණය කළ නොහැක. "
            "මට දිනය සහ මූලාශ්‍රය සමඟ වෙළඳපොළ යොමු මිල පමණක් ලබා දිය හැක."
        )
    return "I can't decide whether you should buy, sell, or borrow. I can provide dated, sourced market reference prices only."


def weather_source_fallback(sinhala: bool) -> str:
    """Fail closed when a generated numeric weather answer loses its attribution."""
    if sinhala:
        return "මූලාශ්‍රය සහ දත්ත දිනය තහවුරු කළ නොහැකි නිසා මට මෙම කාලගුණ දත්ත විශ්වාසයෙන් ලබා දිය නොහැක. නැවත උත්සාහ කරන්න."
    return (
        "I can't provide this weather data because its source and as-of date could not be verified. Please try again."
    )


def diagnosis_boundary(sinhala: bool) -> str:
    """Replace a generated definitive diagnosis with uncertainty-aware guidance."""
    if sinhala:
        return (
            "මෙම ලක්ෂණවලින් පමණක් නිශ්චිත රෝග විනිශ්චයක් කළ නොහැක. "
            "කෘෂිකර්ම උපදේශක හෝ ගොවිජන සේවා මධ්‍යස්ථානයෙන් වගාව පරීක්ෂා කරවා ගන්න."
        )
    return (
        "These symptoms alone are not enough for a definite diagnosis. "
        "Ask an agricultural instructor or Agrarian Services Centre to inspect the crop."
    )


class DomainSafetyPreHook(PreHook):
    """Block high-risk requests before they reach an LLM."""

    async def on_run(
        self,
        session: Session,
        agent: Agent,
        requests: list[AgentRequest],
    ) -> list[AgentRequest] | AgentReply:
        del agent
        text = _raw_text_from_requests(requests)
        normalized = _normalized(text)
        sinhala = session_reply_in_sinhala(session.get_non_volatile_cache(), text)
        if _is_chemical_exposure(normalized):
            return AgentReplyText(response=exposure_referral(sinhala))
        if _is_unsafe_amount_instruction(text, normalized):
            return AgentReplyText(response=chemical_referral(sinhala))
        if _contains_any(normalized, FINANCIAL_DECISION_TERMS) or FINANCIAL_REQUEST_PATTERN.search(text):
            return AgentReplyText(response=financial_boundary(sinhala))
        return requests

    def name(self) -> str:
        return "domain_safety_input"


class DomainSafetyPostHook(PostHook):
    """Fail closed on unsafe or ungrounded generated output."""

    async def on_run(
        self,
        session: Session,
        requests: list[AgentRequest],
        agent: Agent,
        agent_reply: AgentReply,
    ) -> AgentReply:
        del agent
        if not isinstance(agent_reply, AgentReplyText):
            return agent_reply
        reply = agent_reply.response
        request_text = _original_text_from_requests(requests)
        normalized_request = _normalized(request_text)
        normalized_reply = _normalized(reply)
        intent = classify_intent(request_text)
        sinhala = session_reply_in_sinhala(session.get_non_volatile_cache(), request_text)
        if _is_chemical_exposure(normalized_request) or _is_chemical_exposure(normalized_reply):
            return AgentReplyText(response=exposure_referral(sinhala))
        if intent is Intent.CROP_PROBLEM and (
            DEFINITIVE_DIAGNOSIS_PATTERN.search(reply) or UNQUALIFIED_DIAGNOSIS_PATTERN.search(reply)
        ):
            return AgentReplyText(response=diagnosis_boundary(sinhala))
        unsafe_amount = _is_unsafe_amount_instruction(reply, normalized_reply)
        unsafe_product = _contains_any(normalized_reply, AGROCHEMICAL_PRODUCT_TERMS) or bool(
            PRESCRIPTIVE_PRODUCT_PATTERN.search(reply)
        )
        if (
            intent is Intent.WEATHER_ADVICE
            and not _has_dosage_context(normalized_reply)
            and not PRESCRIPTIVE_AMOUNT_PATTERN.search(reply)
            and not unsafe_product
        ):
            # A weather percentage next to a non-prescriptive warning such as "do not decide
            # whether to spray from this forecast alone" is not a chemical concentration.
            unsafe_amount = False
        if unsafe_amount or unsafe_product:
            return AgentReplyText(response=chemical_referral(sinhala))
        if FINANCIAL_DIRECTIVE_PATTERN.search(reply):
            return AgentReplyText(response=financial_boundary(sinhala))
        is_ungrounded_weather_answer = intent is Intent.WEATHER_ADVICE and bool(
            NUMERIC_INFORMATION_PATTERN.search(reply)
        )
        has_source = bool(SOURCE_PATTERN.search(reply))
        has_date = bool(DATE_PATTERN.search(reply))
        if is_ungrounded_weather_answer and not (has_source and has_date):
            return AgentReplyText(response=weather_source_fallback(sinhala))
        if intent is Intent.WEATHER_ADVICE and sinhala:
            cleaned_reply = clean_sinhala_weather_reply(reply)
            if cleaned_reply != reply:
                return AgentReplyText(response=cleaned_reply)
        return agent_reply

    def name(self) -> str:
        return "domain_safety_output"
