import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'middleware'))

from handlers.content_generation import ContentGenerationHandler
from prompt_policies.identity_first import IdentityFirstPolicy
from prompt_policies.reference_first import ReferenceFirstPolicy


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


class TestReferenceFirstPolicy:
    def setup_method(self):
        self.handler = ContentGenerationHandler(FakeFeishu(), {}, {})
        self.policy = ReferenceFirstPolicy('gpt-image-2', self.handler)
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
        self.person_scene = {
            **self.scene,
            '场景描述_中文': '室内奶油风桌面人物场景',
            '人物类型': '有人物·主体',
            '年龄段': '22-26',
            '外貌风格': '短发，通勤妆感',
        }
        self.brief = {
            'consistency_strength': '强',
            'consistency_anchor': {'person': '同一女生，服装和发型保持一致'},
        }

    def test_build_master_prompt_matches_current_gpt_image2_renderer(self):
        expected = self.handler._build_gpt_image2_master_prompt(
            self.strategy, self.sku_fields, self.scene, persona=None, brief=None
        )
        current = self.policy.build_master_prompt(
            self.strategy, self.sku_fields, self.scene, persona=None, brief=None
        )
        assert current == expected

    def test_build_sub_prompts_stays_scene_driven_and_lightweight_for_reference_first(self):
        current = self.policy.build_sub_prompts(
            None, self.person_scene, 3, persona=None, brief=self.brief
        )
        assert len(current) == 3
        assert all(prompt.startswith('第') for prompt in current)
        assert all('室内奶油风桌面人物场景' in prompt for prompt in current)
        assert all('【一致性约束】' not in prompt for prompt in current)
        assert all('同一女生，服装和发型保持一致' not in prompt for prompt in current)
        assert all('商品保持唯一主角' in prompt for prompt in current)


class TestIdentityFirstPolicy:
    def setup_method(self):
        self.handler = ContentGenerationHandler(FakeFeishu(), {}, {})
        self.policy = IdentityFirstPolicy('nanobanana-2', self.handler)
        self.strategy = {'fields': {'情绪基调': '松弛感'}}
        self.sku_fields = {
            '产品简称': '豹纹手机链',
            'SKU名称': 'SJL0413009 豹纹手机链',
            '颜色': ['棕黑'],
            '材质': ['树脂'],
            '风格': ['复古豹纹'],
        }
        self.scene = {
            '场景描述_中文': '室内奶油风桌面人物场景',
            '风格基调词': '干净、精致、生活方式感',
            '排除描述': '禁止多余手部遮挡，禁止主体漂移',
            '人物类型': '有人物·主体',
            '道具建议': '杂志、咖啡杯、首饰托盘',
            '年龄段': '22-26',
            '外貌风格': '短发，通勤妆感',
        }
        self.brief = {
            'consistency_strength': '强',
            'consistency_anchor': {'person': '同一女生，服装和发型保持一致'},
        }

    def test_build_master_prompt_matches_current_nanobanana_renderer(self):
        expected = self.handler._build_nanobanana_master_prompt(
            self.strategy, self.sku_fields, self.scene, persona=None, brief=self.brief
        )
        current = self.policy.build_master_prompt(
            self.strategy, self.sku_fields, self.scene, persona=None, brief=self.brief
        )
        assert current == expected

    def test_build_sub_prompts_keeps_identity_consistency_constraints_for_identity_first(self):
        current = self.policy.build_sub_prompts(
            None, self.scene, 2, persona=None, brief=self.brief
        )
        assert len(current) == 2
        assert all('【一致性约束】' in prompt for prompt in current)
        assert all('同一女生，服装和发型保持一致' in prompt for prompt in current)
