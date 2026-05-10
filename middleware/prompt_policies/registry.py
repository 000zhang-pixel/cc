from core.config import load_model_params


REQUIRED_IMAGE_MODEL_CAPABILITY_KEYS = frozenset({
    'prompt_policy',
    'sub_prompt_identity_lock',
    'primary_reference_mode',
    'adapter_family',
    'reference_input_mode',
    'generation_size_key',
})


DEFAULT_IMAGE_MODEL_CAPABILITY = {
    'prompt_policy': 'identity_first',
    'sub_prompt_identity_lock': True,
    'primary_reference_mode': 'identity_anchor',
    'adapter_family': 'generic',
    'reference_input_mode': 'inline_data',
    'generation_size_key': 'image_size',
}


FALLBACK_IMAGE_MODEL_CAPABILITIES = {}


def validate_image_model_capability(model_name: str, capability) -> list[str]:
    if not isinstance(capability, dict):
        return [f'{model_name} capability must be a dict']
    missing = sorted(REQUIRED_IMAGE_MODEL_CAPABILITY_KEYS - set(capability.keys()))
    if not missing:
        return []
    return [f'{model_name} missing capability keys: {missing}']


def _get_model_params_capability(model_name: str, model_params=None) -> dict:
    effective_model_params = model_params if model_params is not None else load_model_params()
    providers = ((effective_model_params or {}).get('image_model') or {}).get('providers') or {}
    provider_cfg = providers.get(model_name) or {}
    capability = provider_cfg.get('capability') or {}
    if not isinstance(capability, dict):
        return {}
    if validate_image_model_capability(model_name, capability):
        return {}
    return dict(capability)


def get_image_model_capability(model_name: str, override: dict | None = None, model_params=None) -> dict:
    capability = dict(DEFAULT_IMAGE_MODEL_CAPABILITY)
    capability.update(FALLBACK_IMAGE_MODEL_CAPABILITIES.get(model_name, {}))
    capability.update(_get_model_params_capability(model_name, model_params=model_params))
    if override:
        capability.update(override)
    return capability
