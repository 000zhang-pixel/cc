DEFAULT_IMAGE_MODEL_CAPABILITY = {
    'prompt_policy': 'identity_first',
    'sub_prompt_identity_lock': True,
    'primary_reference_mode': 'identity_anchor',
}


IMAGE_MODEL_CAPABILITIES = {
    'gpt-image-2': {
        'prompt_policy': 'reference_first',
        'sub_prompt_identity_lock': False,
        'primary_reference_mode': 'reference_image',
    },
    'nanobanana-2': {
        'prompt_policy': 'identity_first',
        'sub_prompt_identity_lock': True,
        'primary_reference_mode': 'identity_anchor',
    },
}


def _get_model_params_capability(model_name: str, model_params=None) -> dict:
    providers = ((model_params or {}).get('image_model') or {}).get('providers') or {}
    provider_cfg = providers.get(model_name) or {}
    capability = provider_cfg.get('capability') or {}
    return dict(capability)


def get_image_model_capability(model_name: str, override: dict | None = None, model_params=None) -> dict:
    capability = dict(DEFAULT_IMAGE_MODEL_CAPABILITY)
    capability.update(IMAGE_MODEL_CAPABILITIES.get(model_name, {}))
    capability.update(_get_model_params_capability(model_name, model_params=model_params))
    if override:
        capability.update(override)
    return capability
