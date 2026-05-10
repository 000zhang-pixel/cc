from .identity_first import IdentityFirstPolicy
from .reference_first import ReferenceFirstPolicy


def get_image_prompt_policy(model_name: str, handler=None):
    if model_name == 'gpt-image-2':
        return ReferenceFirstPolicy(model_name, handler)
    if model_name == 'nanobanana-2':
        return IdentityFirstPolicy(model_name, handler)
    return IdentityFirstPolicy(model_name, handler)
