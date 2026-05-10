from .base import BaseImagePromptPolicy


class IdentityFirstPolicy(BaseImagePromptPolicy):
    def build_master_prompt(self, strategy, sku_fields, scene, persona=None, brief=None):
        return self.handler._build_nanobanana_master_prompt(
            strategy, sku_fields, scene, persona=persona, brief=brief
        )

    def build_sub_prompts(self, shotplan, scene, img_count, persona=None, brief=None):
        return self.handler._build_image_sub_prompts(
            shotplan, scene, img_count, persona=persona, brief=brief
        )
