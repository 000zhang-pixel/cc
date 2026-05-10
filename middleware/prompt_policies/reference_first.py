from .base import BaseImagePromptPolicy


class ReferenceFirstPolicy(BaseImagePromptPolicy):
    def build_master_prompt(self, strategy, sku_fields, scene, persona=None, brief=None):
        return self.handler._build_gpt_image2_master_prompt(
            strategy, sku_fields, scene, persona=persona, brief=brief
        )

    def build_sub_prompts(self, shotplan, scene, img_count, persona=None, brief=None):
        prompts = self.handler._build_image_sub_prompts(
            shotplan, scene, img_count, persona=persona, brief=None
        )
        return [self._lighten_reference_first_prompt(prompt, scene) for prompt in prompts]

    def _lighten_reference_first_prompt(self, prompt: str, scene: dict) -> str:
        cleaned = prompt
        marker = '，【一致性约束】'
        if marker in cleaned:
            cleaned = cleaned.split(marker, 1)[0]

        person_type = (scene or {}).get('人物类型', '').strip()
        if person_type and not self.handler._is_no_person_scene(person_type):
            cleaned += '，人物仅作场景陪体，商品保持唯一主角'
        return cleaned
