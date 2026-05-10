import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'middleware'))

from handlers.content_generation import ContentGenerationHandler


class FakeFeishu:
    def get_options(self, record, field_name):
        return record.get('fields', {}).get(field_name, []) or []

    def get_option(self, record, field_name):
        value = record.get('fields', {}).get(field_name, '')
        if isinstance(value, list):
            return value[0] if value else ''
        return value or ''

    def get_text(self, record, field_name):
        value = record.get('fields', {}).get(field_name, '')
        if isinstance(value, list):
            return '、'.join(str(v) for v in value)
        return '' if value is None else str(value)


class ImagePromptRendererTests(unittest.TestCase):
    def setUp(self):
        self.handler = ContentGenerationHandler(FakeFeishu(), {}, {})
        self.strategy = {'fields': {'情绪基调': '松弛感'}}
        self.sku_fields = {
            '产品简称': '豹纹手机链',
            'SKU名称': 'SJL0413009 豹纹手机链',
            '颜色': ['棕黑'],
            '材质': ['树脂'],
            '风格': ['复古豹纹'],
        }
        self.scene = {
            '场景描述_中文': '室内奶油风桌面静物场景',
            '风格基调词': '干净、精致、生活方式感',
            '排除描述': '禁止多余手部遮挡，禁止主体漂移',
            '人物类型': '无人物',
            '道具建议': '杂志、咖啡杯、首饰托盘',
        }

    def test_model_specific_master_prompt_renderer_differs_between_gpt_image2_and_nanobanana(self):
        gpt_prompt = self.handler._build_model_aware_image_master_prompt(
            'gpt-image-2', self.strategy, self.sku_fields, self.scene, persona=None, brief=None
        )
        nanobanana_prompt = self.handler._build_model_aware_image_master_prompt(
            'nanobanana-2', self.strategy, self.sku_fields, self.scene, persona=None, brief=None
        )

        self.assertIn('白底图', gpt_prompt)
        self.assertIn('参考图', gpt_prompt)
        self.assertIn('【一致性要求】', nanobanana_prompt)
        self.assertNotEqual(gpt_prompt, nanobanana_prompt)

    def test_sub_prompts_remain_shared_and_scene_driven_in_phase1(self):
        sub_prompts = self.handler._build_image_sub_prompts(
            shotplan=None, scene=self.scene, img_count=3, persona=None, brief=None
        )

        self.assertEqual(len(sub_prompts), 3)
        self.assertTrue(all(prompt.startswith('第') for prompt in sub_prompts))
        self.assertTrue(all('室内奶油风桌面静物场景' in prompt for prompt in sub_prompts))
        self.assertTrue(all('【一致性约束】' not in prompt for prompt in sub_prompts))


if __name__ == '__main__':
    unittest.main()
