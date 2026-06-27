import os
import json

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
SETTINGS_FILE = os.path.join(DATA_DIR, 'ai_settings.json')

ALLOWED_PROVIDERS = {'anthropic', 'openai', 'gemini', 'openrouter'}

DEFAULT_MODELS = {
    'anthropic': 'claude-sonnet-4-20250514',
    'openai': 'gpt-4o-mini',
    'gemini': 'gemini-2.0-flash',
    'openrouter': 'openai/gpt-4o-mini',
}


def _load_env():
    """Load .env file into os.environ if it exists."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    parts = line.split('=', 1)
                    if len(parts) == 2:
                        os.environ[parts[0].strip()] = parts[1].strip()


PROVIDER_ENV_MAP = {
    'anthropic': 'ANTHROPIC_API_KEY',
    'openai': 'OPENAI_API_KEY',
    'gemini': 'GEMINI_API_KEY',
    'openrouter': 'OPENROUTER_API_KEY',
}


def get_api_key_for_provider(provider):
    """Get API key from .env for a specific provider."""
    _load_env()
    env_var = PROVIDER_ENV_MAP.get(provider)
    if env_var:
        return (os.environ.get(env_var) or '').strip()
    return ''


def get_masked_api_key(api_key):
    if not api_key or len(api_key) <= 8:
        return api_key
    return api_key[:4] + '***' + api_key[-4:]


def get_default_settings():
    """Membaca default AI settings dari file .env di root project."""
    _load_env()

    provider = (os.environ.get('AI_PROVIDER') or '').strip().lower()
    model = (os.environ.get('AI_MODEL') or '').strip()
    api_key = get_api_key_for_provider(provider)

    all_keys = {}
    for prov, env_var in PROVIDER_ENV_MAP.items():
        val = (os.environ.get(env_var) or '').strip()
        if val:
            all_keys[prov] = val

    if not provider or not api_key:
        if all_keys:
            provider = list(all_keys.keys())[0]
            api_key = all_keys[provider]
        else:
            return None

    return {
        'provider': provider,
        'api_key': api_key,
        'model': model or DEFAULT_MODELS.get(provider, ''),
        'all_keys': all_keys,
    }


def get_ai_settings(user_id):
    """Always return default settings from .env (no per-user settings)."""
    return get_default_settings()


def save_ai_settings(user_id, provider, api_key, model):
    """No-op: settings are read-only from .env."""
    pass
