import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'middleware'))

from prompt_policies.factory import get_image_prompt_policy
from prompt_policies.identity_first import IdentityFirstPolicy
from prompt_policies.reference_first import ReferenceFirstPolicy


def test_prompt_policy_factory_returns_reference_first_for_gpt_image2():
    policy = get_image_prompt_policy('gpt-image-2')
    assert isinstance(policy, ReferenceFirstPolicy)


def test_prompt_policy_factory_returns_identity_first_for_nanobanana2():
    policy = get_image_prompt_policy('nanobanana-2')
    assert isinstance(policy, IdentityFirstPolicy)


def test_prompt_policy_factory_falls_back_to_identity_first_for_unknown_models():
    policy = get_image_prompt_policy('some-future-model')
    assert isinstance(policy, IdentityFirstPolicy)
