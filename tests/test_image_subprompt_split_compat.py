import sys
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


class TestImageSubPromptSplitCompatibility:
    def setup_method(self):
        self.handler = ContentGenerationHandler(FakeFeishu(), {}, {})
        self.scene = {
            '场景描述_中文': '室内奶油风桌面静物场景',
            '风格基调词': '干净、精致、生活方式感',
            '排除描述': '禁止多余手部遮挡，禁止主体漂移',
            '人物类型': '无人物',
            '道具建议': '杂志、咖啡杯、首饰托盘',
        }

    def test_gpt_image2_model_aware_sub_prompts_now_strip_identity_lock_for_reference_first(self):
        current = self.handler._build_model_aware_image_sub_prompts(
            'gpt-image-2', None, {
                **self.scene,
                '场景描述_中文': '室内奶油风桌面人物场景',
                '人物类型': '有人物·主体',
                '年龄段': '22-26',
                '外貌风格': '短发，通勤妆感',
            }, 3, persona=None, brief={
                'consistency_strength': '强',
                'consistency_anchor': {'person': '同一女生，服装和发型保持一致'},
            }
        )
        assert len(current) == 3
        assert all('【一致性约束】' not in prompt for prompt in current)
        assert all('商品保持唯一主角' in prompt for prompt in current)

    def test_nanobanana_model_aware_sub_prompts_match_legacy_shared_builder_for_now(self):
        scene = {
            **self.scene,
            '人物类型': '有人物·主体',
            '年龄段': '22-26',
            '外貌风格': '短发，通勤妆感',
        }
        brief = {
            'consistency_strength': '强',
            'consistency_anchor': {'person': '同一女生，服装和发型保持一致'},
        }
        legacy = self.handler._build_image_sub_prompts(None, scene, 1, persona=None, brief=brief)
        current = self.handler._build_model_aware_image_sub_prompts(
            'nanobanana-2', None, scene, 1, persona=None, brief=brief
        )
        assert current == legacy
