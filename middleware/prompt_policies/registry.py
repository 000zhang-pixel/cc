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


def get_image_model_capability(model_name: str, override: dict | None = None) -> dict:
    capability = dict(DEFAULT_IMAGE_MODEL_CAPABILITY)
    capability.update(IMAGE_MODEL_CAPABILITIES.get(model_name, {}))
    if override:
        capability.update(override)
    return capability
