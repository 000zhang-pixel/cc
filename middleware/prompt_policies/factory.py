from .identity_first import IdentityFirstPolicy
from .reference_first import ReferenceFirstPolicy
from .registry import get_image_model_capability


def get_image_prompt_policy(model_name: str, handler=None, capability: dict | None = None):
    resolved_capability = get_image_model_capability(model_name, override=capability)
    prompt_policy = resolved_capability.get('prompt_policy')
    if prompt_policy == 'reference_first':
        return ReferenceFirstPolicy(model_name, handler)
    return IdentityFirstPolicy(model_name, handler)
