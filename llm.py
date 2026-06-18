import base64
import logging
import re
import threading

from google import genai
from google.genai import types

import config

_log = logging.getLogger("llm")
_clients: dict = {}
_lock = threading.Lock()

QUOTA_MSG = "⚠️ 模型額度用完了（429 配額耗盡）。請到控制台「模型路由」把模型切到本地 Ollama 或等免費額度重置後再試。"


def is_quota_error(e) -> bool:
    """例外是否為模型額度／配額耗盡（429 / RESOURCE_EXHAUSTED / quota）。各呼叫端共用此單一判定。"""
    s = str(e).lower()
    return "429" in s or "resource_exhausted" in s or "quota" in s or "exceeded your current" in s


def _openai_base_url() -> str:
    """OpenAI 端點：空值明確用官方端點，避免空字串 OPENAI_BASE_URL 環境變數被 SDK 取走→空 URL。"""
    base = (config.OPENAI_BASE_URL or "").strip()
    return base if base else "https://api.openai.com/v1"


# list_available_models：給面板列出「實際能用的對話模型」，逐供應商容錯。
_GOOGLE_EXCLUDE = ("embedding", "tts", "image", "audio", "robotics",
                   "lyria", "live", "computer-use", "deep-research", "customtools")
_OPENAI_CHAT_PREFIXES = ("gpt-", "o1", "o3", "o4", "chatgpt")
_OPENAI_EXCLUDE = ("embedding", "tts", "whisper", "dall-e", "image", "audio",
                   "realtime", "transcribe", "moderation", "search", "instruct")


def _list_google_models() -> list:
    if not config.GEMINI_API_KEY:
        return []
    out = []
    for m in _get_client("google").models.list():
        name = (getattr(m, "name", "") or "").replace("models/", "")
        actions = getattr(m, "supported_actions", None) or []
        if "generateContent" in actions and not any(x in name for x in _GOOGLE_EXCLUDE):
            out.append(name)
    return out


def _list_anthropic_models() -> list:
    if not config.ANTHROPIC_API_KEY:
        return []
    return [m.id for m in _get_client("anthropic").models.list().data]


def _list_openai_models() -> list:
    if not config.OPENAI_API_KEY:
        return []
    out = []
    for m in _get_client("openai").models.list().data:
        mid = m.id
        if mid.startswith(_OPENAI_CHAT_PREFIXES) and not any(x in mid for x in _OPENAI_EXCLUDE):
            out.append(mid)
    return out


# 精簡清單：砍「帶日期的快照」（有未帶日期同名時）與「公認舊世代」，避免 picker 被洗版。
_DATE_SUFFIX = re.compile(r"(-\d{4}-\d{2}-\d{2}|-\d{8}|-\d{4})$")


def _is_legacy(m: str) -> bool:
    return m == "gpt-4" or m.startswith(("gpt-3.5", "gpt-4-", "gemini-2.0"))


def _prune_models(ids: list) -> list:
    """去舊世代 + 去日期快照（有未帶日期同名才砍；只有日期版的保留）。保序。"""
    kept = [m for m in ids if not _is_legacy(m)]
    bases = set(kept)
    out = []
    for m in kept:
        base = _DATE_SUFFIX.sub("", m)
        if base != m and base in bases:
            continue                      # 有未帶日期同名 → 丟掉這個日期快照
        out.append(m)
    return out


def list_available_models() -> dict:
    """列出有設金鑰之供應商的對話模型（逐家容錯，並精簡舊世代/日期快照）。
    回 {"models":[...], "providers":{name:count}}。"""
    providers, models = {}, set()
    for name, fn in (("google", _list_google_models),
                     ("anthropic", _list_anthropic_models),
                     ("openai", _list_openai_models)):
        try:
            got = _prune_models(fn())
        except Exception:
            got = []
        if got:
            providers[name] = len(got)
            models.update(got)
    return {"models": sorted(models), "providers": providers}


def _provider_of(model: str) -> str:
    """依模型名判定供應商：claude-*→anthropic、gpt-*/o*→openai、gemini-*→google。
    其餘未知前綴：設了 OPENAI_BASE_URL（第三方相容端點，如 siraya）就走該端點，否則 google。"""
    m = model.lower()
    if m.startswith("claude"):
        return "anthropic"
    if m.startswith("gpt") or m.startswith("o"):
        return "openai"
    if m.startswith("gemini"):
        return "google"
    return "openai" if config.OPENAI_BASE_URL else "google"


def _get_client(provider: str):
    if provider not in _clients:
        with _lock:
            if provider not in _clients:
                if provider == "google":
                    if config.GEMINI_API_KEY:
                        _clients[provider] = genai.Client(api_key=config.GEMINI_API_KEY)
                    else:
                        _clients[provider] = genai.Client(
                            vertexai=True,
                            project=config.GCP_PROJECT,
                            location=config.GCP_LOCATION,
                        )
                elif provider == "anthropic":
                    if not config.ANTHROPIC_API_KEY:
                        raise RuntimeError("ANTHROPIC_API_KEY 未設定，無法使用 claude-* 模型")
                    import anthropic
                    _clients[provider] = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
                else:
                    # 本地相容端點（如 Ollama）不驗金鑰，但 SDK 要求非空 → 用慣例假值
                    key = config.OPENAI_API_KEY or ("ollama" if config.OPENAI_BASE_URL else "")
                    if not key:
                        raise RuntimeError("OPENAI_API_KEY 未設定，無法使用 gpt-*/o* 模型")
                    import openai
                    _clients[provider] = openai.OpenAI(
                        api_key=key,
                        base_url=_openai_base_url())   # 空值明確用官方端點，避免空字串環境變數毒化
    return _clients[provider]


# ── Google ───────────────────────────────────────────────────
def _to_contents(messages: list[dict], image_bytes: bytes | None):
    contents = []
    for m in messages:
        role = "model" if m["role"] == "assistant" else "user"
        contents.append(types.Content(role=role, parts=[types.Part(text=str(m["content"]))]))
    if image_bytes is not None:
        if not contents or contents[-1].role != "user":
            contents.append(types.Content(role="user", parts=[]))
        contents[-1].parts.append(
            types.Part(inline_data=types.Blob(mime_type="image/jpeg", data=image_bytes))
        )
    return contents


# Gemma 4（gemma-4-*）是思考型模型：會先吐 ~140+ 思考 token 才到答案，且思考無法關閉
# （thinking_budget=0 會 500）。輸出上限太小（分類常用 8~256）會被思考吃光→空輸出/500。
# 故對 Gemma 把輸出上限拉到足夠容下「思考＋答案」的下限。
_GEMMA_MIN_OUTPUT_TOKENS = 1024


def _effective_max_tokens(model: str, requested: int) -> int:
    if "gemma" in model.lower():
        return max(requested, _GEMMA_MIN_OUTPUT_TOKENS)
    return requested


def _gen_google(model, system, messages, image_bytes, max_output_tokens):
    cfg = types.GenerateContentConfig(
        system_instruction=system,
        max_output_tokens=_effective_max_tokens(model, max_output_tokens),
    )
    resp = _get_client("google").models.generate_content(
        model=model,
        contents=_to_contents(messages, image_bytes),
        config=cfg,
    )
    return (resp.text or "").strip()


# ── Anthropic ────────────────────────────────────────────────
def _to_anthropic_messages(messages: list[dict], image_bytes: bytes | None):
    msgs = [{"role": "assistant" if m["role"] == "assistant" else "user",
             "content": str(m["content"])} for m in messages]
    if image_bytes is not None:
        if not msgs or msgs[-1]["role"] != "user":
            msgs.append({"role": "user", "content": ""})
        text = msgs[-1]["content"]
        msgs[-1]["content"] = [
            {"type": "image", "source": {
                "type": "base64", "media_type": "image/jpeg",
                "data": base64.b64encode(image_bytes).decode()}},
            {"type": "text", "text": text or "（圖片）"},
        ]
    return msgs


def _gen_anthropic(model, system, messages, image_bytes, max_output_tokens):
    resp = _get_client("anthropic").messages.create(
        model=model, max_tokens=max_output_tokens, system=system,
        messages=_to_anthropic_messages(messages, image_bytes))
    return "".join(b.text for b in resp.content if b.type == "text").strip()


# ── OpenAI ───────────────────────────────────────────────────
def _to_openai_messages(system: str, messages: list[dict], image_bytes: bytes | None):
    msgs = [{"role": "system", "content": system}]
    msgs += [{"role": m["role"], "content": str(m["content"])} for m in messages]
    if image_bytes is not None:
        if msgs[-1]["role"] != "user":
            msgs.append({"role": "user", "content": ""})
        text = msgs[-1]["content"]
        b64 = base64.b64encode(image_bytes).decode()
        msgs[-1]["content"] = [
            {"type": "text", "text": text or "（圖片）"},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        ]
    return msgs


def _gen_openai(model, system, messages, image_bytes, max_output_tokens):
    resp = _get_client("openai").chat.completions.create(
        model=model,
        messages=_to_openai_messages(system, messages, image_bytes),
        max_completion_tokens=max_output_tokens)
    return (resp.choices[0].message.content or "").strip()


# ── 公開介面（供應商無關，呼叫端不變） ─────────────────────────
def generate(model: str, system: str, messages: list[dict],
             image_bytes: bytes | None = None, max_output_tokens: int = 2048) -> str:
    provider = _provider_of(model)
    endpoint = config.OPENAI_BASE_URL if (provider == "openai" and config.OPENAI_BASE_URL) else provider
    _log.info("LLM call: model=%s provider=%s endpoint=%s", model, provider, endpoint)
    if provider == "anthropic":
        return _gen_anthropic(model=model, system=system, messages=messages,
                              image_bytes=image_bytes, max_output_tokens=max_output_tokens)
    if provider == "openai":
        return _gen_openai(model=model, system=system, messages=messages,
                           image_bytes=image_bytes, max_output_tokens=max_output_tokens)
    return _gen_google(model=model, system=system, messages=messages,
                       image_bytes=image_bytes, max_output_tokens=max_output_tokens)
