# 爆款分析增强 + 批量学习 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完善爆款素材图片视觉分析（替换 placeholder），并新增 `scripts/batch_learn.py` 脚本，将表6爆款分析结果 AI 汇总后写入引擎表8/9/10。

**Architecture:** Feature 1 在 `MaterialAnalysisHandler` 里插入图片分析链路：新增 `VisionModelAdapter`（OpenAI-compatible，base64图片输入）和 `FeishuClient.download_attachment()`，由 `main.py` 注入。Feature 2 是独立 CLI 脚本 `scripts/batch_learn.py`，通过 `sys.path` 复用 middleware 模块，无新依赖。

**Tech Stack:** Python 3.12+, openai SDK, httpx, lark-oapi, unittest.mock

---

## File Map

| 文件 | 操作 | 说明 |
|------|------|------|
| `middleware/config/model_params.yaml` | Modify | 追加 `vision_model` 节 |
| `middleware/adapters/ai_models.py` | Modify | 新增 `VisionModelAdapter`、`build_vision_adapter()` |
| `middleware/adapters/feishu.py` | Modify | 构造函数保存 app_id/secret；新增 `download_attachment()` |
| `middleware/handlers/material_analysis.py` | Modify | 实现图片下载+分析，替换 placeholder |
| `middleware/main.py` | Modify | 构建 VisionModelAdapter 并注入 handler |
| `scripts/batch_learn.py` | Create | 批量学习主脚本 |
| `middleware/tests/test_batch_learn.py` | Create | 批量学习纯逻辑单元测试 |

---

## Task 1: VisionModelAdapter

**Files:**
- Modify: `middleware/adapters/ai_models.py`
- Modify: `middleware/config/model_params.yaml`

- [ ] **Step 1: 追加 `vision_model` 节到 model_params.yaml**

在 `middleware/config/model_params.yaml` 末尾追加：

```yaml
vision_model:
  max_concurrency: 1
  retry_max: 2
  retry_base_seconds: 1
  providers:
    kimi-vision:
      api_key: ${KIMI_API_KEY}
      base_url: https://api.moonshot.cn/v1
      model: moonshot-v1-8k-vision-preview
      max_tokens: 1024
```

- [ ] **Step 2: 在 `ai_models.py` 末尾（工厂函数之前）插入 `VisionModelAdapter`**

在 `middleware/adapters/ai_models.py` 的 `# Factory` 注释行之前插入：

```python
# ---------------------------------------------------------------------------
# Vision model adapter (OpenAI-compatible, supports base64 image in messages)
# ---------------------------------------------------------------------------

class VisionModelAdapter:
    """
    Sends an image (raw bytes) + text prompt to an OpenAI-compatible vision model.
    Returns the assistant's text response.
    """

    def __init__(self, cfg: dict, shared_cfg: dict):
        self._client = OpenAI(
            api_key=cfg["api_key"],
            base_url=cfg.get("base_url", "https://api.openai.com/v1"),
        )
        self._model = cfg["model"]
        self._max_tokens = cfg.get("max_tokens", 1024)
        self._semaphore = _get_semaphore("vision", shared_cfg["max_concurrency"])
        self._retry_max = shared_cfg["retry_max"]
        self._retry_base = shared_cfg["retry_base_seconds"]

    def analyze(self, system: str, user_text: str, image_bytes: bytes) -> str:
        """Send image + text to vision model. Returns assistant text."""
        import base64
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        image_url = f"data:image/jpeg;base64,{b64}"

        def _call():
            with self._semaphore:
                resp = self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": system},
                        {
                            "role": "user",
                            "content": [
                                {"type": "image_url", "image_url": {"url": image_url}},
                                {"type": "text", "text": user_text},
                            ],
                        },
                    ],
                    max_tokens=self._max_tokens,
                )
                return resp.choices[0].message.content or ""

        return _with_retry(_call, self._retry_max, self._retry_base)
```

- [ ] **Step 3: 追加 `build_vision_adapter()` 工厂函数**

在 `ai_models.py` 末尾已有的 `build_video_adapter()` 之后追加：

```python
def build_vision_adapter(model_params: dict) -> "VisionModelAdapter | None":
    """Returns VisionModelAdapter for the first configured vision provider, or None if not configured."""
    cfg_root = model_params.get("vision_model")
    if not cfg_root:
        return None
    providers = cfg_root.get("providers", {})
    if not providers:
        return None
    provider_cfg = next(iter(providers.values()))
    # Skip if api_key is still an unexpanded placeholder
    if not provider_cfg.get("api_key") or "${" in str(provider_cfg.get("api_key", "")):
        return None
    return VisionModelAdapter(provider_cfg, cfg_root)
```

- [ ] **Step 4: 验证语法**

```bash
cd d:/claude_code/middleware
python -c "from adapters.ai_models import VisionModelAdapter, build_vision_adapter; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
cd d:/claude_code
git add middleware/adapters/ai_models.py middleware/config/model_params.yaml
git commit -m "feat: add VisionModelAdapter + build_vision_adapter + vision_model config"
```

---

## Task 2: FeishuClient.download_attachment()

**Files:**
- Modify: `middleware/adapters/feishu.py`

- [ ] **Step 1: 在 FeishuClient.__init__ 中保存 app_id / app_secret**

在 `feishu.py` 中找到 `__init__` 方法，在 `self.base_token = base_token` 之后加两行：

```python
    def __init__(self, app_id: str, app_secret: str, base_token: str):
        self.base_token = base_token
        self._app_id = app_id        # 新增
        self._app_secret = app_secret  # 新增
        self._client = lark.Client.builder() \
```

- [ ] **Step 2: 在 FeishuClient 末尾追加 download_attachment()**

在 `feishu.py` `get_number` 方法（最后一个方法）之后追加：

```python
    def download_attachment(self, file_token: str) -> bytes:
        """
        Download an attachment from Feishu Drive by file_token.
        Raises RuntimeError on failure.
        """
        import httpx

        # 1. Get tenant_access_token
        token_resp = httpx.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": self._app_id, "app_secret": self._app_secret},
            timeout=10,
        )
        token_resp.raise_for_status()
        access_token = token_resp.json().get("tenant_access_token", "")
        if not access_token:
            raise RuntimeError(f"Failed to get tenant_access_token: {token_resp.text}")

        # 2. Download the file
        dl_resp = httpx.get(
            f"https://open.feishu.cn/open-apis/drive/v1/medias/{file_token}/download",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )
        dl_resp.raise_for_status()
        return dl_resp.content
```

- [ ] **Step 3: 验证语法**

```bash
cd d:/claude_code/middleware
python -c "from adapters.feishu import FeishuClient; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
cd d:/claude_code
git add middleware/adapters/feishu.py
git commit -m "feat: FeishuClient stores app credentials + download_attachment()"
```

---

## Task 3: MaterialAnalysisHandler 图片分析 + main.py 注入

**Files:**
- Modify: `middleware/handlers/material_analysis.py`
- Modify: `middleware/main.py`

- [ ] **Step 1: 更新 MaterialAnalysisHandler.__init__ 接受 vision_adapter**

将 `material_analysis.py` 的 `__init__` 改为：

```python
class MaterialAnalysisHandler:
    def __init__(
        self,
        feishu: FeishuClient,
        tables: dict,
        model_params: dict,
        vision_adapter=None,   # VisionModelAdapter | None
    ):
        self._feishu = feishu
        self._tables = tables
        self._model_params = model_params
        self._vision = vision_adapter  # None → skip image analysis
```

- [ ] **Step 2: 在 _run() 中替换 placeholder 调用**

找到 `material_analysis.py` 的 `_run()` 方法中的这段代码：

```python
        # 4. Image analysis (placeholder — real implementation needs attachment download)
        image_analysis: dict = {}
        if has_attachment:
            image_analysis = self._analyze_image_placeholder()
```

替换为：

```python
        # 4. Image analysis — download attachment and call vision model
        image_analysis: dict = {}
        if has_attachment and self._vision is not None:
            try:
                attachments = rec["fields"].get("素材附件", [])
                file_token = ""
                if isinstance(attachments, list) and attachments:
                    first = attachments[0]
                    file_token = first.get("file_token", "") if isinstance(first, dict) else ""
                if file_token:
                    image_bytes = self._feishu.download_attachment(file_token)
                    image_analysis = self._analyze_image(image_bytes)
            except Exception as exc:
                logger.warning("Image analysis skipped for record %s: %s", record_id, exc)
```

- [ ] **Step 3: 实现 _analyze_image() 替换 placeholder**

将 `material_analysis.py` 末尾的 `_analyze_image_placeholder` 方法替换为：

```python
    def _analyze_image(self, image_bytes: bytes) -> dict:
        system = (
            "你是一名电商内容视觉分析专家。请严格按 JSON 格式输出，不要有其他文字。"
        )
        user_text = (
            "请分析这张电商种草内容的截图，输出 JSON：\n"
            "{\n"
            '  "composition": "构图风格，如：平铺/斜角/场景融入/特写",\n'
            '  "tone": "色调氛围，如：明亮清新/暗调高级/粉嫩少女/自然原木",\n'
            '  "props": "场景与道具描述，简洁一句话"\n'
            "}"
        )
        try:
            raw = self._vision.analyze(system, user_text, image_bytes)
            return self._parse_json(raw)
        except Exception as exc:
            logger.warning("Vision AI call failed: %s", exc)
            return {}
```

- [ ] **Step 4: 更新 main.py 注入 VisionModelAdapter**

在 `main.py` 中找到 import 部分，添加：

```python
from adapters.ai_models import build_vision_adapter
```

然后在 `main()` 函数中找到 `# --- Build handlers ---` 注释之前，插入：

```python
    vision_adapter = build_vision_adapter(model_params)
    if vision_adapter:
        logger.info("VisionModelAdapter initialized.")
    else:
        logger.info("VisionModelAdapter not configured — image analysis disabled.")
```

最后找到 `TASK_MATERIAL_ANALYSIS` 那行，改为：

```python
        TASK_MATERIAL_ANALYSIS: MaterialAnalysisHandler(feishu, tables, model_params, vision_adapter),
```

- [ ] **Step 5: 验证语法**

```bash
cd d:/claude_code/middleware
python -c "
from handlers.material_analysis import MaterialAnalysisHandler
from adapters.feishu import FeishuClient
print('OK')
"
```

Expected: `OK`

- [ ] **Step 6: 验证 main.py 能正常启动（dry-run import）**

```bash
cd d:/claude_code/middleware
python -c "import main; print('import OK')"
```

Expected: `import OK`

- [ ] **Step 7: Commit**

```bash
cd d:/claude_code
git add middleware/handlers/material_analysis.py middleware/main.py
git commit -m "feat: implement image analysis in MaterialAnalysisHandler via VisionModelAdapter"
```

---

## Task 4: scripts/batch_learn.py

**Files:**
- Create: `scripts/batch_learn.py`

- [ ] **Step 1: 创建 scripts/batch_learn.py**

```python
#!/usr/bin/env python3
"""
批量学习脚本：读取表6所有「分析状态=已完成」的爆款记录，
AI 汇总规律后在引擎表8/9/10 创建新记录（停用状态，供人工审核）。

用法：
    cd d:/claude_code
    python scripts/batch_learn.py
"""
import json
import logging
import os
import re
import sys
from datetime import date

# 复用 middleware 模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "middleware"))

from core.config import load_system, load_model_params
from adapters.feishu import FeishuClient
from adapters.ai_models import build_text_adapter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("batch_learn")

MIN_RECORDS = 3


def main():
    sys_cfg = load_system()
    model_params = load_model_params()
    fc = sys_cfg["feishu"]
    feishu = FeishuClient(fc["app_id"], fc["app_secret"], fc["base_token"])
    tables = fc["tables"]

    # 1. 拉取表6已完成记录
    records = fetch_completed_materials(feishu, tables["material"])
    if len(records) < MIN_RECORDS:
        log.warning(
            "仅找到 %d 条已完成爆款记录（最少需要 %d 条）。请先分析更多爆款后再运行。",
            len(records), MIN_RECORDS,
        )
        sys.exit(0)
    log.info("找到 %d 条已完成爆款记录，开始汇总…", len(records))

    # 2. 构建汇总文本
    summary = build_summary(feishu, records)

    # 3. 调用 AI
    provider = list(model_params["text_model"]["providers"].keys())[0]
    adapter = build_text_adapter(provider, model_params)
    result = call_ai(adapter, summary, len(records))

    # 4. 拉取现有引擎记录（去重用）
    existing = fetch_existing_engine_records(feishu, tables)

    # 5. 写入引擎表
    today = date.today().isoformat()
    n = len(records)
    created = {"strategy": 0, "shotplan": 0, "scene": 0}
    skipped = {"strategy": 0, "shotplan": 0, "scene": 0}

    for s in result.get("strategies", []):
        if is_duplicate_strategy(s, existing["strategies"]):
            skipped["strategy"] += 1
            log.info("跳过重复 Strategy: %s", s.get("策略名称", ""))
        else:
            fields = {**s}
            fields["是否启用"] = "停用"
            fields["优先级"] = 5
            fields["备注"] = f"来源：爆款批量学习 {today}，基于 {n} 条爆款"
            if isinstance(fields.get("文案叙事节点"), list):
                fields["文案叙事节点"] = json.dumps(fields["文案叙事节点"], ensure_ascii=False)
            try:
                feishu.create_record(tables["strategy"], fields)
                created["strategy"] += 1
                log.info("新建 Strategy: %s", s.get("策略名称", ""))
            except Exception as exc:
                log.error("创建 Strategy 失败: %s — %s", s.get("策略名称", ""), exc)

    for sp in result.get("shotplans", []):
        if is_duplicate_shotplan(sp, existing["shotplans"]):
            skipped["shotplan"] += 1
            log.info("跳过重复 ShotPlan: %s", sp.get("方案名称", ""))
        else:
            fields = {**sp}
            fields["是否启用"] = "停用"
            fields["备注"] = f"来源：爆款批量学习 {today}"
            if isinstance(fields.get("角色序列"), list):
                fields["节点数量"] = len(fields["角色序列"])
                fields["角色序列"] = json.dumps(fields["角色序列"], ensure_ascii=False)
            try:
                feishu.create_record(tables["shotplan"], fields)
                created["shotplan"] += 1
                log.info("新建 ShotPlan: %s", sp.get("方案名称", ""))
            except Exception as exc:
                log.error("创建 ShotPlan 失败: %s — %s", sp.get("方案名称", ""), exc)

    for sc in result.get("scenes", []):
        if is_duplicate_scene(sc, existing["scenes"]):
            skipped["scene"] += 1
            log.info("跳过重复 Scene: %s", sc.get("场景名称", ""))
        else:
            fields = {**sc}
            fields["是否启用"] = "停用"
            fields.setdefault("权重", 5)
            fields["备注"] = f"来源：爆款批量学习 {today}"
            try:
                feishu.create_record(tables["scene"], fields)
                created["scene"] += 1
                log.info("新建 Scene: %s", sc.get("场景名称", ""))
            except Exception as exc:
                log.error("创建 Scene 失败: %s — %s", sc.get("场景名称", ""), exc)

    # 6. 报告
    print("\n" + "=" * 40)
    print("批量学习完成")
    print("=" * 40)
    print(f"Strategy : 新建 {created['strategy']} 条，跳过（重复）{skipped['strategy']} 条")
    print(f"ShotPlan : 新建 {created['shotplan']} 条，跳过（重复）{skipped['shotplan']} 条")
    print(f"Scene    : 新建 {created['scene']} 条，跳过（重复）{skipped['scene']} 条")
    print("所有新记录已设为「停用」，请在飞书引擎表审核后手动启用。")


# ---------------------------------------------------------------------------
# 纯逻辑函数（可单元测试）
# ---------------------------------------------------------------------------

def fetch_completed_materials(feishu: FeishuClient, table_id: str) -> list[dict]:
    records = feishu.list_records(table_id)
    return [r for r in records if feishu.get_option(r, "分析状态") == "已完成"]


def build_summary(feishu: FeishuClient, records: list[dict]) -> str:
    """Build a compact multi-line summary of viral material records for AI input."""
    lines = []
    for i, rec in enumerate(records, 1):
        parts = [
            f"品类:{feishu.get_option(rec, '品类') or '未知'}",
            f"内容类型:{feishu.get_option(rec, '内容类型') or '未知'}",
            f"标题公式:{feishu.get_text(rec, '标题公式') or '未知'}",
            f"正文结构:{feishu.get_text(rec, '正文结构') or '未知'}",
            f"情绪:{','.join(feishu.get_options(rec, '情绪触发点')) or '未知'}",
            f"卖点:{feishu.get_option(rec, '卖点提炼方式') or '未知'}",
        ]
        composition = feishu.get_text(rec, "构图风格")
        tone = feishu.get_text(rec, "色调氛围")
        if composition:
            parts.append(f"构图:{composition}")
        if tone:
            parts.append(f"色调:{tone}")
        lines.append(f"[{i}] " + " | ".join(parts))
    return "\n".join(lines)


def call_ai(adapter, summary: str, n: int) -> dict:
    """Call text AI to synthesize new engine records from viral content summary."""
    system = (
        "你是一名电商内容策略专家。请严格按 JSON 格式输出，不要有其他文字。"
        "输出内容将直接写入内容引擎表格，务必规范。"
    )
    user = (
        f"以下是 {n} 条爆款内容的分析摘要，请提炼共同规律，输出可用于内容生成引擎的新记录。\n\n"
        f"--- 爆款摘要 ---\n{summary}\n\n"
        "要求：\n"
        "1. strategies 输出 1-2 条，代表最显著的文案策略规律\n"
        "2. shotplans 输出 1 条，代表最常见的图片分镜序列\n"
        "3. scenes 输出 1-2 条，代表最典型的视觉场景风格\n\n"
        "输出 JSON（严格格式，所有字段必须填写）：\n"
        "{\n"
        '  "strategies": [\n'
        '    {\n'
        '      "策略名称": "简短名称（10字以内）",\n'
        '      "切入角度": "精致生活|学生平价|极限测评|社交货币|实用主义|情感共鸣 中选一",\n'
        '      "情绪基调": "松弛感|兴奋感|专业理性|温暖亲密|高冷极简|活泼俏皮 中选一",\n'
        '      "表达方式": "生活记录感种草|干货测评|朋友推荐|场景故事|对比揭秘|教程攻略 中选一",\n'
        '      "系统提示词前缀": "你是一名专注于[风格]电商种草内容的写作专家，擅长[特点]。",\n'
        '      "文案叙事节点": [{"index":1,"zh":"开篇","guidance":"用场景/痛点引入"},{"index":2,"zh":"产品介绍","guidance":"突出核心卖点"},{"index":3,"zh":"使用体验","guidance":"具体感受描述"},{"index":4,"zh":"结尾推荐","guidance":"CTA引导收藏购买"}],\n'
        '      "适用内容类型": ["种草推荐"],\n'
        '      "适用平台": ["小红书"],\n'
        '      "适用品类": ["手机壳"]\n'
        '    }\n'
        '  ],\n'
        '  "shotplans": [\n'
        '    {\n'
        '      "方案名称": "简短名称",\n'
        '      "适用内容形态": ["图片生成"],\n'
        '      "适用内容类型": ["种草推荐"],\n'
        '      "适用品类": ["手机壳"],\n'
        '      "角色序列": [\n'
        '        {"index":1,"en":"Close-up product shot showing details, {scene_description}"},\n'
        '        {"index":2,"en":"Lifestyle flat lay with props, {scene_description}"},\n'
        '        {"index":3,"en":"In-hand usage shot, {scene_description}"}\n'
        '      ]\n'
        '    }\n'
        '  ],\n'
        '  "scenes": [\n'
        '    {\n'
        '      "场景名称": "简短名称",\n'
        '      "适用品类": ["手机壳"],\n'
        '      "适用平台": ["小红书"],\n'
        '      "场景基底_英文": "Bright minimalist desk setup with soft natural light, clean white background",\n'
        '      "风格基调词": "clean, bright, minimalist, lifestyle",\n'
        '      "排除描述": "avoid dark background, avoid clutter, avoid shadows",\n'
        '      "场景描述_中文": "明亮简约桌面，自然光，白色背景"\n'
        '    }\n'
        '  ]\n'
        "}"
    )
    raw = adapter.complete(system, user)
    result = _parse_json(raw)
    if not result:
        log.error("AI 返回内容无法解析为 JSON，原始输出：\n%s", raw[:1000])
        sys.exit(1)
    return result


def fetch_existing_engine_records(feishu: FeishuClient, tables: dict) -> dict:
    return {
        "strategies": feishu.list_records(tables["strategy"]),
        "shotplans": feishu.list_records(tables["shotplan"]),
        "scenes": feishu.list_records(tables["scene"]),
    }


def is_duplicate_strategy(new: dict, existing: list[dict]) -> bool:
    """Dedup by (frozenset(适用品类), 切入角度, 情绪基调)."""
    new_cats = frozenset(new.get("适用品类", []))
    new_angle = new.get("切入角度", "").strip()
    new_tone = new.get("情绪基调", "").strip()

    for rec in existing:
        fields = rec.get("fields", {})
        ex_cats = frozenset(_extract_multiselect(fields.get("适用品类")))
        ex_angle = _extract_option(fields.get("切入角度"))
        ex_tone = _extract_option(fields.get("情绪基调"))
        if new_cats == ex_cats and new_angle == ex_angle and new_tone == ex_tone:
            return True
    return False


def is_duplicate_shotplan(new: dict, existing: list[dict]) -> bool:
    """Dedup by (frozenset(适用品类), frozenset(适用内容形态))."""
    new_cats = frozenset(new.get("适用品类", []))
    new_forms = frozenset(new.get("适用内容形态", []))

    for rec in existing:
        fields = rec.get("fields", {})
        ex_cats = frozenset(_extract_multiselect(fields.get("适用品类")))
        ex_forms = frozenset(_extract_multiselect(fields.get("适用内容形态")))
        if new_cats == ex_cats and new_forms == ex_forms:
            return True
    return False


def is_duplicate_scene(new: dict, existing: list[dict]) -> bool:
    """Dedup by 场景名称 exact match."""
    new_name = new.get("场景名称", "").strip()
    for rec in existing:
        fields = rec.get("fields", {})
        ex_raw = fields.get("场景名称", "")
        # Field may be rich-text list or plain string
        if isinstance(ex_raw, list):
            ex_name = "".join(
                seg.get("text", "") for seg in ex_raw if isinstance(seg, dict)
            )
        else:
            ex_name = str(ex_raw)
        if new_name == ex_name.strip():
            return True
    return False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_option(val) -> str:
    """Extract string value from a Feishu single-select field (dict or str)."""
    if val is None:
        return ""
    if isinstance(val, dict):
        return val.get("text", "")
    return str(val)


def _extract_multiselect(val) -> list[str]:
    """Extract list of strings from a Feishu multi-select field."""
    if not val:
        return []
    if isinstance(val, list):
        return [
            v.get("text", "") if isinstance(v, dict) else str(v)
            for v in val
        ]
    return []


def _parse_json(text: str) -> dict:
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {}


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 验证脚本语法**

```bash
cd d:/claude_code
python -c "import scripts.batch_learn" 2>/dev/null || python scripts/batch_learn.py --help 2>/dev/null || python -c "
import sys, os
sys.path.insert(0, 'scripts')
sys.path.insert(0, 'middleware')
import batch_learn
print('syntax OK')
"
```

Expected: `syntax OK`

- [ ] **Step 3: Commit**

```bash
cd d:/claude_code
git add scripts/batch_learn.py
git commit -m "feat: add batch_learn.py — AI synthesizes viral patterns into engine tables 8/9/10"
```

---

## Task 5: 单元测试

**Files:**
- Create: `middleware/tests/test_batch_learn.py`

- [ ] **Step 1: 创建单元测试文件**

```python
"""
Unit tests for batch_learn.py pure logic functions.
No Feishu API calls or AI calls.
"""
import sys
import os
import json
import pytest

# Add both scripts/ and middleware/ to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Import pure functions from batch_learn
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
from batch_learn import (
    build_summary,
    is_duplicate_strategy,
    is_duplicate_shotplan,
    is_duplicate_scene,
    _parse_json,
    _extract_option,
    _extract_multiselect,
)
from adapters.feishu import FeishuClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_feishu() -> FeishuClient:
    """Create a FeishuClient with dummy credentials (helper methods don't call API)."""
    return FeishuClient("dummy_id", "dummy_secret", "dummy_token")


def _make_record(fields: dict) -> dict:
    return {"record_id": "recXXX", "fields": fields}


# ---------------------------------------------------------------------------
# _parse_json
# ---------------------------------------------------------------------------

def test_parse_json_plain():
    result = _parse_json('{"key": "value"}')
    assert result == {"key": "value"}


def test_parse_json_with_surrounding_text():
    result = _parse_json('Here is the result: {"key": "value"} done.')
    assert result == {"key": "value"}


def test_parse_json_empty_on_invalid():
    result = _parse_json("not json at all")
    assert result == {}


# ---------------------------------------------------------------------------
# _extract_option / _extract_multiselect
# ---------------------------------------------------------------------------

def test_extract_option_dict():
    assert _extract_option({"text": "手机壳"}) == "手机壳"


def test_extract_option_string():
    assert _extract_option("手机壳") == "手机壳"


def test_extract_option_none():
    assert _extract_option(None) == ""


def test_extract_multiselect_list_of_dicts():
    val = [{"text": "小红书"}, {"text": "得物"}]
    assert set(_extract_multiselect(val)) == {"小红书", "得物"}


def test_extract_multiselect_empty():
    assert _extract_multiselect(None) == []
    assert _extract_multiselect([]) == []


# ---------------------------------------------------------------------------
# is_duplicate_strategy
# ---------------------------------------------------------------------------

def test_is_duplicate_strategy_exact_match():
    new = {"适用品类": ["手机壳"], "切入角度": "精致生活", "情绪基调": "松弛感"}
    existing = [_make_record({
        "适用品类": [{"text": "手机壳"}],
        "切入角度": {"text": "精致生活"},
        "情绪基调": {"text": "松弛感"},
    })]
    assert is_duplicate_strategy(new, existing) is True


def test_is_duplicate_strategy_different_tone():
    new = {"适用品类": ["手机壳"], "切入角度": "精致生活", "情绪基调": "兴奋感"}
    existing = [_make_record({
        "适用品类": [{"text": "手机壳"}],
        "切入角度": {"text": "精致生活"},
        "情绪基调": {"text": "松弛感"},
    })]
    assert is_duplicate_strategy(new, existing) is False


def test_is_duplicate_strategy_empty_existing():
    new = {"适用品类": ["手机壳"], "切入角度": "精致生活", "情绪基调": "松弛感"}
    assert is_duplicate_strategy(new, []) is False


# ---------------------------------------------------------------------------
# is_duplicate_shotplan
# ---------------------------------------------------------------------------

def test_is_duplicate_shotplan_match():
    new = {"适用品类": ["手机壳"], "适用内容形态": ["图片生成"]}
    existing = [_make_record({
        "适用品类": [{"text": "手机壳"}],
        "适用内容形态": [{"text": "图片生成"}],
    })]
    assert is_duplicate_shotplan(new, existing) is True


def test_is_duplicate_shotplan_different_category():
    new = {"适用品类": ["手机挂架"], "适用内容形态": ["图片生成"]}
    existing = [_make_record({
        "适用品类": [{"text": "手机壳"}],
        "适用内容形态": [{"text": "图片生成"}],
    })]
    assert is_duplicate_shotplan(new, existing) is False


# ---------------------------------------------------------------------------
# is_duplicate_scene
# ---------------------------------------------------------------------------

def test_is_duplicate_scene_match():
    new = {"场景名称": "明亮桌面场景"}
    existing = [_make_record({"场景名称": "明亮桌面场景"})]
    assert is_duplicate_scene(new, existing) is True


def test_is_duplicate_scene_rich_text():
    new = {"场景名称": "明亮桌面场景"}
    existing = [_make_record({"场景名称": [{"text": "明亮桌面场景"}]})]
    assert is_duplicate_scene(new, existing) is True


def test_is_duplicate_scene_no_match():
    new = {"场景名称": "户外场景"}
    existing = [_make_record({"场景名称": "明亮桌面场景"})]
    assert is_duplicate_scene(new, existing) is False


# ---------------------------------------------------------------------------
# build_summary
# ---------------------------------------------------------------------------

def test_build_summary_basic():
    feishu = _make_feishu()
    records = [
        _make_record({
            "品类": {"text": "手机壳"},
            "内容类型": {"text": "种草推荐"},
            "标题公式": "数字列表",
            "正文结构": "场景带入→产品→效果",
            "情绪触发点": [{"text": "共鸣"}, {"text": "焦虑"}],
            "卖点提炼方式": {"text": "场景型"},
        })
    ]
    summary = build_summary(feishu, records)
    assert "[1]" in summary
    assert "手机壳" in summary
    assert "种草推荐" in summary
    assert "数字列表" in summary
    assert "共鸣" in summary


def test_build_summary_multiple_records():
    feishu = _make_feishu()
    records = [
        _make_record({"品类": {"text": "手机壳"}, "内容类型": {"text": "种草推荐"}}),
        _make_record({"品类": {"text": "手机挂架"}, "内容类型": {"text": "好物分享"}}),
    ]
    summary = build_summary(feishu, records)
    assert "[1]" in summary
    assert "[2]" in summary
    assert "手机挂架" in summary
```

- [ ] **Step 2: 运行测试**

```bash
cd d:/claude_code/middleware
python -m pytest tests/test_batch_learn.py -v
```

Expected output（所有测试通过）：

```
tests/test_batch_learn.py::test_parse_json_plain PASSED
tests/test_batch_learn.py::test_parse_json_with_surrounding_text PASSED
tests/test_batch_learn.py::test_parse_json_empty_on_invalid PASSED
tests/test_batch_learn.py::test_extract_option_dict PASSED
tests/test_batch_learn.py::test_extract_option_string PASSED
tests/test_batch_learn.py::test_extract_option_none PASSED
tests/test_batch_learn.py::test_extract_multiselect_list_of_dicts PASSED
tests/test_batch_learn.py::test_extract_multiselect_empty PASSED
tests/test_batch_learn.py::test_is_duplicate_strategy_exact_match PASSED
tests/test_batch_learn.py::test_is_duplicate_strategy_different_tone PASSED
tests/test_batch_learn.py::test_is_duplicate_strategy_empty_existing PASSED
tests/test_batch_learn.py::test_is_duplicate_shotplan_match PASSED
tests/test_batch_learn.py::test_is_duplicate_shotplan_different_category PASSED
tests/test_batch_learn.py::test_is_duplicate_scene_match PASSED
tests/test_batch_learn.py::test_is_duplicate_scene_rich_text PASSED
tests/test_batch_learn.py::test_is_duplicate_scene_no_match PASSED
tests/test_batch_learn.py::test_build_summary_basic PASSED
tests/test_batch_learn.py::test_build_summary_multiple_records PASSED
18 passed
```

- [ ] **Step 3: Commit**

```bash
cd d:/claude_code
git add middleware/tests/test_batch_learn.py
git commit -m "test: unit tests for batch_learn pure logic (dedup, summary, json parsing)"
```

---

## Self-Review

**Spec coverage 检查：**
- ✅ 图片视觉分析（飞书附件下载 → 视觉模型 → 填构图风格/色调氛围/场景道具）→ Task 1-3
- ✅ VisionModelAdapter + build_vision_adapter() → Task 1
- ✅ FeishuClient.download_attachment() → Task 2
- ✅ model_params.yaml vision_model 节 → Task 1
- ✅ main.py 注入 VisionModelAdapter → Task 3
- ✅ batch_learn.py 手动触发批量学习 → Task 4
- ✅ 读表6已完成记录 → Task 4
- ✅ AI 汇总 → 写表8/9/10 停用新记录 → Task 4
- ✅ 去重逻辑 → Task 4 + Task 5 测试
- ✅ 错误处理（图片分析失败不影响文本分析、batch_learn 单条失败继续）→ Task 3-4

**Placeholder 扫描：** 无 TBD/TODO。

**类型一致性：** `VisionModelAdapter.analyze()` 在 Task 1 定义，Task 3 调用 `self._vision.analyze()`；`FeishuClient.download_attachment(file_token)` 在 Task 2 定义，Task 3 调用 `self._feishu.download_attachment(file_token)` — 一致。
