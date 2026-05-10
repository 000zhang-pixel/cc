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


class TestImageModelPolicyContract:
    def setup_method(self):
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

    def test_handler_model_aware_prompt_can_route_from_model_params_capability(self):
        self.handler._model_params = {
            'image_model': {
                'providers': {
                    'some-future-model': {
                        'capability': {
                            'prompt_policy': 'reference_first',
                            'sub_prompt_identity_lock': False,
                            'primary_reference_mode': 'reference_image',
                        }
                    }
                }
            }
        }

        prompt = self.handler._build_model_aware_image_master_prompt(
            'some-future-model', self.strategy, self.sku_fields, self.scene, persona=None, brief=None
        )

        assert '参考图任务：白底图即商品参考图' in prompt

    def test_model_aware_master_prompt_contract_keeps_current_renderer_split(self):
        gpt_prompt = self.handler._build_model_aware_image_master_prompt(
            'gpt-image-2', self.strategy, self.sku_fields, self.scene, persona=None, brief=None
        )
        nanobanana_prompt = self.handler._build_model_aware_image_master_prompt(
            'nanobanana-2', self.strategy, self.sku_fields, self.scene, persona=None, brief=None
        )

        assert '参考图任务：白底图即商品参考图' in gpt_prompt
        assert '【一致性要求】' in nanobanana_prompt
        assert gpt_prompt != nanobanana_prompt

    def test_model_aware_sub_prompts_contract_returns_count_aligned_scene_driven_prompts(self):
        prompts = self.handler._build_model_aware_image_sub_prompts(
            'gpt-image-2', shotplan=None, scene=self.scene, img_count=3, persona=None, brief=None
        )

        assert len(prompts) == 3
        assert all(prompt.startswith('第') for prompt in prompts)
        assert all('室内奶油风桌面静物场景' in prompt for prompt in prompts)

    def test_sub_prompts_now_split_between_reference_first_and_identity_first(self):
        gpt_prompts = self.handler._build_model_aware_image_sub_prompts(
            'gpt-image-2', shotplan=None, scene={
                **self.scene,
                '场景描述_中文': '室内奶油风桌面人物场景',
                '人物类型': '有人物·主体',
                '年龄段': '22-26',
                '外貌风格': '短发，通勤妆感',
            }, img_count=1, persona=None, brief={
                'consistency_strength': '强',
                'consistency_anchor': {'person': '同一女生，服装和发型保持一致'},
            }
        )
        nanobanana_prompts = self.handler._build_model_aware_image_sub_prompts(
            'nanobanana-2', shotplan=None, scene={
                **self.scene,
                '场景描述_中文': '室内奶油风桌面人物场景',
                '人物类型': '有人物·主体',
                '年龄段': '22-26',
                '外貌风格': '短发，通勤妆感',
            }, img_count=1, persona=None, brief={
                'consistency_strength': '强',
                'consistency_anchor': {'person': '同一女生，服装和发型保持一致'},
            }
        )

        assert '【一致性约束】' not in gpt_prompts[0]
        assert '商品保持唯一主角' in gpt_prompts[0]
        assert '【一致性约束】' in nanobanana_prompts[0]
        assert gpt_prompts[0] != nanobanana_prompts[0]
