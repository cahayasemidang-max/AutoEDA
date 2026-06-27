import requests
import json
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo


class AIClientError(Exception):
    pass


class QuotaExceededError(AIClientError):
    def __init__(self, message, reset_in_seconds=None):
        self.reset_in_seconds = reset_in_seconds
        self.reset_time_iso = None
        if reset_in_seconds:
            self.reset_time_iso = (datetime.now(timezone.utc) + timedelta(seconds=reset_in_seconds)).isoformat()
        super().__init__(message)


DEFAULT_MODELS = {
    'anthropic': 'claude-sonnet-4-20250514',
    'openai': 'gpt-4o-mini',
    'gemini': 'gemini-2.5-flash',
    'openrouter': 'openai/gpt-4o-mini',
}


def call_ai(provider, api_key, model, system_prompt, user_prompt):
    if not api_key:
        raise AIClientError('API key tidak boleh kosong.')

    if not model:
        model = DEFAULT_MODELS.get(provider, '')

    try:
        if provider == 'anthropic':
            return _call_anthropic(api_key, model, system_prompt, user_prompt)
        elif provider == 'openai':
            return _call_openai(api_key, model, system_prompt, user_prompt)
        elif provider == 'gemini':
            return _call_gemini(api_key, model, system_prompt, user_prompt)
        elif provider == 'openrouter':
            return _call_openrouter(api_key, model, system_prompt, user_prompt)
        else:
            raise AIClientError(f"Provider '{provider}' tidak didukung.")
    except AIClientError:
        raise
    except Exception as e:
        raise AIClientError(f'Gagal memanggil AI: {str(e)}')


def _call_anthropic(api_key, model, system_prompt, user_prompt):
    import anthropic
    client = anthropic.Anthropic(api_key=api_key, timeout=120)
    message = client.messages.create(
        model=model,
        max_tokens=2048,
        system=system_prompt,
        messages=[{'role': 'user', 'content': user_prompt}],
    )
    return message.content[0].text


def _call_openai(api_key, model, system_prompt, user_prompt):
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ],
        'max_tokens': 2048,
    }
    resp = requests.post(
        'https://api.openai.com/v1/chat/completions',
        headers=headers,
        json=payload,
        timeout=60,
    )
    if resp.status_code != 200:
        raise AIClientError(f'OpenAI API error: {resp.status_code}')
    data = resp.json()
    return data['choices'][0]['message']['content']


def _get_next_pacific_midnight_seconds():
    now_utc = datetime.now(timezone.utc)
    pacific = ZoneInfo('America/Los_Angeles')
    now_pacific = datetime.now(pacific)
    tomorrow = now_pacific.date() + timedelta(days=1)
    midnight_pacific = datetime.combine(tomorrow, datetime.min.time(), tzinfo=pacific)
    delta = midnight_pacific - now_pacific
    return int(delta.total_seconds())


def _call_gemini(api_key, model, system_prompt, user_prompt):
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}'
    payload = {
        'system_instruction': {
            'parts': [{'text': system_prompt}]
        },
        'contents': [{
            'parts': [{'text': user_prompt}]
        }],
        'generationConfig': {
            'maxOutputTokens': 4096,
            'temperature': 0.4,
        },
    }
    resp = requests.post(url, json=payload, timeout=60)
    if resp.status_code == 429:
        reset_in = _get_next_pacific_midnight_seconds()
        hours = reset_in // 3600
        minutes = (reset_in % 3600) // 60
        msg = (
            f'Kuota gratis harian Gemini telah habis. '
            f'Kuota akan tersedia kembali dalam ±{hours} jam {minutes} menit '
            f'(reset tengah malam waktu Pasifik).'
        )
        raise QuotaExceededError(msg, reset_in)
    if resp.status_code != 200:
        detail = resp.text[:500]
        raise AIClientError(f'Gemini API error: {resp.status_code} - {detail}')
    data = resp.json()
    candidates = data.get('candidates', [])
    if not candidates:
        raise AIClientError('Gemini: tidak ada kandidat respons.')
    parts = candidates[0].get('content', {}).get('parts', [])
    return ''.join(p.get('text', '') for p in parts)


def _call_openrouter(api_key, model, system_prompt, user_prompt):
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ],
        'max_tokens': 2048,
    }
    resp = requests.post(
        'https://openrouter.ai/api/v1/chat/completions',
        headers=headers,
        json=payload,
        timeout=60,
    )
    if resp.status_code != 200:
        raise AIClientError(f'OpenRouter API error: {resp.status_code}')
    data = resp.json()
    return data['choices'][0]['message']['content']
