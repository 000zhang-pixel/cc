#!/usr/bin/env python3
"""Expand 手机链 strategy/shotplan/scene/persona data and normalize priority scales.

Default mode is dry-run.
Use --apply to write to Feishu live tables.

Scope:
- Add ST035-ST038, SP044-SP047, SC104-SC111, PS017-PS020
- Normalize selected legacy 手机链 priorities/weights to the current 80-scale family
- Idempotent by code field (create missing, update existing)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any

ROOT = "/Users/carson/workspace/ai-content-hub"
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from dotenv import load_dotenv
from middleware.adapters.feishu import FeishuClient
from middleware.core.config import load_system

load_dotenv(os.path.join(ROOT, ".env"), override=False)

TABLES = {
    "strategy": {"id": "tblu2EzR78tWjYf6", "code": "策略编号"},
    "shotplan": {"id": "tbl0xCaqru1TjwzK", "code": "方案编号"},
    "scene": {"id": "tbliWlwiyA4sppgY", "code": "场景编号"},
    "persona": {"id": "tblxSbOoZ2kMCkc6", "code": "人设编号"},
}


@dataclass
class SyncPlan:
    table_key: str
    create_or_update: list[dict[str, Any]]
    updates_by_code: dict[str, dict[str, Any]]


STRATEGIES = [
    {
        "策略编号": "ST035",
        "策略名称": "通勤解放双手型",
        "切入角度": "实用主义",
        "情绪基调": "松弛感",
        "表达方式": "场景故事",
        "系统提示词前缀": "围绕主营品类手机壳/手机链生成具体、可执行、平台友好的高信息密度文案。",
        "文案叙事节点": json.dumps(["通勤痛点", "上身展示", "便利变化", "收尾种草"], ensure_ascii=False),
        "适用内容类型": ["通勤穿搭", "场景展示", "种草推荐"],
        "适用平台": ["小红书", "得物"],
        "适用品类": ["手机链"],
        "是否启用": "启用",
        "优先级": 80,
        "备注": "手机链专项新增：强化解放双手、地铁电梯办公室连续场景的真实便利感。",
        "标题写作指南": "标题优先写具体通勤情境、使用变化和谁适合。",
        "叙事角度标签": ["实用变化", "通勤代入"],
        "结构模式": "问题解决",
        "标题句式池": "通勤时真的离不开这条手机链\n挤地铁还能随手拿手机的秘密\n上班路上越用越顺手的手机链",
        "正文禁忌": "避免只夸颜值不写场景，避免脱离真实通勤动作。",
        "差异化提示模板": "围绕解放双手与通勤效率展开，优先写电梯/地铁/拿咖啡/刷卡这些具体动作变化。",
        "人设适配标签": ["通勤", "极简", "松弛"],
    },
    {
        "策略编号": "ST036",
        "策略名称": "周末出游随拍出片型",
        "切入角度": "生活方式",
        "情绪基调": "轻松日常",
        "表达方式": "生活记录感种草",
        "系统提示词前缀": "围绕主营品类手机壳/手机链生成具体、可执行、平台友好的高信息密度文案。",
        "文案叙事节点": json.dumps(["出游氛围", "人物上身", "链条细节", "出片总结"], ensure_ascii=False),
        "适用内容类型": ["出游记录", "场景展示", "种草推荐"],
        "适用平台": ["小红书", "得物"],
        "适用品类": ["手机链"],
        "是否启用": "启用",
        "优先级": 76,
        "备注": "手机链专项新增：服务 citywalk/市集/海边/展览等轻出游内容。",
        "标题写作指南": "标题写清周末出游场景、随手出片感和搭配价值。",
        "叙事角度标签": ["生活方式", "氛围感种草"],
        "结构模式": "场景切入",
        "标题句式池": "周末出门我会默认带这条手机链\ncitywalk 随手拍都很搭的手机链\n轻出游真的很需要这种顺手感",
        "正文禁忌": "避免写成纯景点游记，主体仍要回到手机链如何参与出行。",
        "差异化提示模板": "围绕周末出游与随手出片感展开，优先写行走、拍照、拿饮品、换场景时的连续使用。",
        "人设适配标签": ["文艺", "户外", "街头"],
    },
    {
        "策略编号": "ST037",
        "策略名称": "礼服晚间氛围点睛型",
        "切入角度": "精致生活",
        "情绪基调": "精致考究",
        "表达方式": "视觉展示型",
        "系统提示词前缀": "围绕主营品类手机壳/手机链生成具体、可执行、平台友好的高信息密度文案。",
        "文案叙事节点": json.dumps(["晚间氛围", "整体造型", "链条光感", "点睛总结"], ensure_ascii=False),
        "适用内容类型": ["约会穿搭", "场景展示", "好物分享"],
        "适用平台": ["小红书", "得物"],
        "适用品类": ["手机链"],
        "是否启用": "启用",
        "优先级": 72,
        "备注": "手机链专项新增：覆盖晚餐约会、酒吧外景、夜间活动等低光精致场景。",
        "标题写作指南": "标题优先突出夜晚、精致穿搭和整体造型被点亮的感觉。",
        "叙事角度标签": ["搭配点睛", "夜间氛围"],
        "结构模式": "情绪切入",
        "标题句式池": "晚上出门更容易被这条手机链点到\n夜里灯光下真的很显质感\n精致约会穿搭别忽略手机链这一步",
        "正文禁忌": "避免把焦点完全放到妆发或夜景，链条要有明确视觉作用。",
        "差异化提示模板": "围绕夜间灯光下的金属光泽、穿搭完整度和精致氛围展开，避免白天逻辑复用。",
        "人设适配标签": ["精致", "甜酷", "夜景"],
    },
    {
        "策略编号": "ST038",
        "策略名称": "闺蜜同款社交扩散型",
        "切入角度": "社交货币",
        "情绪基调": "活泼俏皮",
        "表达方式": "朋友推荐",
        "系统提示词前缀": "围绕主营品类手机壳/手机链生成具体、可执行、平台友好的高信息密度文案。",
        "文案叙事节点": json.dumps(["同框亮相", "款式呼应", "互动反馈", "拉人种草"], ensure_ascii=False),
        "适用内容类型": ["闺蜜同款", "种草推荐", "场景展示"],
        "适用平台": ["小红书", "得物"],
        "适用品类": ["手机链"],
        "是否启用": "启用",
        "优先级": 72,
        "备注": "手机链专项新增：强调双人同款、互拍、互相安利带来的社交扩散性。",
        "标题写作指南": "标题写清双人同款关系、互动感和被问链接的结果。",
        "叙事角度标签": ["闺蜜同款", "社交扩散"],
        "结构模式": "人物关系",
        "标题句式池": "和闺蜜一起用真的会更想安利\n双人同款手机链出门太容易被问\n这种一起买一起挂的快乐很具体",
        "正文禁忌": "避免只有产品并排图，必须体现双人互动或真实同框。",
        "差异化提示模板": "围绕闺蜜互拍、同款呼应和社交反馈展开，优先写双人关系感。",
        "人设适配标签": ["青春", "甜酷", "社交"],
    },
]

STRATEGY_PRIORITY_UPDATES = {
    "ST021": 76,
    "ST022": 76,
    "ST023": 76,
    "ST024": 72,
    "ST025": 72,
    "ST026": 72,
    "ST027": 68,
    "ST028": 68,
    "ST029": 72,
    "ST030": 76,
}

SHOTPLANS = [
    {
        "方案编号": "SP044",
        "方案名称": "手机链通勤效率5图",
        "适用内容形态": ["图片"],
        "适用内容类型": ["通勤穿搭", "场景展示"],
        "适用品类": ["手机链"],
        "角色序列": json.dumps([
            {"index": 1, "zh": "电梯或写字楼入口整体亮相，手持挂链手机同步出镜，{scene_description}", "en": "电梯或写字楼入口整体亮相，手持挂链手机同步出镜，{scene_description}"},
            {"index": 2, "zh": "刷卡、拿咖啡或开门动作中展示手机链顺手感，{scene_description}", "en": "刷卡、拿咖啡或开门动作中展示手机链顺手感，{scene_description}"},
            {"index": 3, "zh": "挂点、链条垂坠和上机状态近景特写，{scene_description}", "en": "挂点、链条垂坠和上机状态近景特写，{scene_description}"},
            {"index": 4, "zh": "切换到地铁/工位/走廊第二场景，强化连续通勤使用，{scene_description}", "en": "切换到地铁/工位/走廊第二场景，强化连续通勤使用，{scene_description}"},
            {"index": 5, "zh": "通勤收尾图，突出解放双手和整套穿搭完成度，{scene_description}", "en": "通勤收尾图，突出解放双手和整套穿搭完成度，{scene_description}"},
        ], ensure_ascii=False),
        "节点数量": 5,
        "是否启用": "启用",
        "备注": "手机链新增方案：适配通勤效率与真实动作变化。",
        "构图节奏": "丰富",
        "人物出镜比例": "中等",
        "近中远景配比": "近景2 / 中景2 / 远景1",
        "道具密度": "中",
        "动作变化要求": "至少覆盖走动、停留、取用手机三类动作，避免全组只有静态摆拍。",
        "禁止重复镜头": "避免连续相同电梯镜面角度、重复手持角度和纯背景产品图。",
    },
    {
        "方案编号": "SP045",
        "方案名称": "手机链周末出游6图",
        "适用内容形态": ["图片"],
        "适用内容类型": ["出游记录", "场景展示"],
        "适用品类": ["手机链"],
        "角色序列": json.dumps([
            {"index": 1, "zh": "出游场景首图亮相，手机链与整体穿搭同步出现，{scene_description}", "en": "出游场景首图亮相，手机链与整体穿搭同步出现，{scene_description}"},
            {"index": 2, "zh": "边走边拍或拿饮品时的自然使用状态，{scene_description}", "en": "边走边拍或拿饮品时的自然使用状态，{scene_description}"},
            {"index": 3, "zh": "手机链上机细节和材质近景，{scene_description}", "en": "手机链上机细节和材质近景，{scene_description}"},
            {"index": 4, "zh": "切换第二地点或第二动作，强化周末流动感，{scene_description}", "en": "切换第二地点或第二动作，强化周末流动感，{scene_description}"},
            {"index": 5, "zh": "半身或全身人物图，链条垂坠与氛围同框，{scene_description}", "en": "半身或全身人物图，链条垂坠与氛围同框，{scene_description}"},
            {"index": 6, "zh": "轻松收尾，突出这条手机链陪完整个出游过程，{scene_description}", "en": "轻松收尾，突出这条手机链陪完整个出游过程，{scene_description}"},
        ], ensure_ascii=False),
        "节点数量": 6,
        "是否启用": "启用",
        "备注": "手机链新增方案：适配 citywalk/市集/展览等轻出游内容。",
        "构图节奏": "丰富",
        "人物出镜比例": "中等",
        "近中远景配比": "近景2 / 中景3 / 远景1",
        "道具密度": "中",
        "动作变化要求": "至少覆盖行走、驻足、拿手机/饮品三类状态，形成连续日常流。",
        "禁止重复镜头": "避免连续相同街拍角度、重复纯行走图和没有手机同框的链条孤立图。",
    },
    {
        "方案编号": "SP046",
        "方案名称": "手机链夜间约会5图",
        "适用内容形态": ["图片"],
        "适用内容类型": ["约会穿搭", "场景展示"],
        "适用品类": ["手机链"],
        "角色序列": json.dumps([
            {"index": 1, "zh": "夜间场景整体亮相，手机链与穿搭同步出镜，{scene_description}", "en": "夜间场景整体亮相，手机链与穿搭同步出镜，{scene_description}"},
            {"index": 2, "zh": "窗边灯光或门口等待时的半身持机镜头，{scene_description}", "en": "窗边灯光或门口等待时的半身持机镜头，{scene_description}"},
            {"index": 3, "zh": "链条在低光环境下的金属光泽近景特写，{scene_description}", "en": "链条在低光环境下的金属光泽近景特写，{scene_description}"},
            {"index": 4, "zh": "切换坐姿或回头动作，突出夜间氛围与垂坠感，{scene_description}", "en": "切换坐姿或回头动作，突出夜间氛围与垂坠感，{scene_description}"},
            {"index": 5, "zh": "约会收尾图，强调整体造型被手机链点亮，{scene_description}", "en": "约会收尾图，强调整体造型被手机链点亮，{scene_description}"},
        ], ensure_ascii=False),
        "节点数量": 5,
        "是否启用": "启用",
        "备注": "手机链新增方案：适配夜景、约会、餐酒馆等低光精致内容。",
        "构图节奏": "丰富",
        "人物出镜比例": "中等",
        "近中远景配比": "近景2 / 中景2 / 远景1",
        "道具密度": "中",
        "动作变化要求": "至少覆盖站姿、坐姿、回头或举机动作，避免整组都在同一位置。",
        "禁止重复镜头": "避免连续相同灯牌背景、重复正面站立和纯环境夜景图。",
    },
    {
        "方案编号": "SP047",
        "方案名称": "手机链闺蜜同款互动5图",
        "适用内容形态": ["图片"],
        "适用内容类型": ["闺蜜同款", "种草推荐"],
        "适用品类": ["手机链"],
        "角色序列": json.dumps([
            {"index": 1, "zh": "双人同框整体亮相，两条手机链同步可见，{scene_description}", "en": "双人同框整体亮相，两条手机链同步可见，{scene_description}"},
            {"index": 2, "zh": "互拍或一起看手机的互动镜头，{scene_description}", "en": "互拍或一起看手机的互动镜头，{scene_description}"},
            {"index": 3, "zh": "两条手机链近景对比，展示颜色或风格呼应，{scene_description}", "en": "两条手机链近景对比，展示颜色或风格呼应，{scene_description}"},
            {"index": 4, "zh": "切换第二个动作或走动态，增强社交真实感，{scene_description}", "en": "切换第二个动作或走动态，增强社交真实感，{scene_description}"},
            {"index": 5, "zh": "双人收尾图，强调同款出门的氛围和安利感，{scene_description}", "en": "双人收尾图，强调同款出门的氛围和安利感，{scene_description}"},
        ], ensure_ascii=False),
        "节点数量": 5,
        "是否启用": "启用",
        "备注": "手机链新增方案：适配双人同款、互拍安利、社交扩散内容。",
        "构图节奏": "丰富",
        "人物出镜比例": "高",
        "近中远景配比": "近景1 / 中景3 / 远景1",
        "道具密度": "中",
        "动作变化要求": "至少覆盖并肩、互动、行走三种双人状态，避免全程站桩同框。",
        "禁止重复镜头": "避免连续相同双人站位、重复并排静态图和看不清两条链的镜头。",
    },
]

SCENES = [
    {
        "场景编号": "SC104",
        "场景名称": "人物·通勤电梯口刷卡持机",
        "是否启用": "启用",
        "权重": 80,
        "适用品类": ["手机链"],
        "适用平台": ["得物", "小红书"],
        "使用频次": 0,
        "人物类型": "真人出镜",
        "年龄段": "23-28岁职场",
        "性别倾向": "女性",
        "外貌风格": "利落都市妆感，黑发或深棕发，干净职业气质",
        "姿态倾向": "自然站立/刷卡动作",
        "场景类型": "室内·工作室",
        "时段光境": "白天",
        "空间感": "室内公共空间",
        "光源类型": "室内灯光",
        "光线方向": "正面均匀补光",
        "色温": "中性白(5500K)",
        "景别": "中景/半身",
        "拍摄角度": "平视",
        "景深感": "中景深·适度虚化",
        "镜头感": "50mm自然视角",
        "场景基底_英文": "young office woman at elevator lobby tapping access card while holding phone with chain, clean corporate interior, neat commute styling, realistic urban morning rhythm",
        "风格基调词": "通勤,效率,职场松弛",
        "排除描述": "不要过度商务摆拍，不要工牌遮挡手机链，不要背景人群过于拥挤",
        "场景描述_中文": "职场女生在电梯口刷卡进入办公区，另一只手自然持挂链手机，手机链顺手垂落，整体呈现高效但不紧绷的通勤感。",
        "备注": "新增通勤主场景，高权重 evergreen。",
        "服装风格": "极简通勤、西装外套或衬衫",
        "身体展示重点": "上半身与手部动作",
        "着装禁忌": "避免过度暴露或夸张礼服感",
        "场景主题": "通勤",
        "氛围等级": "中",
        "道具建议": "门禁卡、咖啡杯、工位包",
        "光线风格标签": ["干净", "通勤"],
        "适合人设标签": ["通勤", "极简", "白领"],
        "差异化备注": "强调刷卡动作和单手取机便利性。",
    },
    {
        "场景编号": "SC105",
        "场景名称": "人物·地铁站台单手拿咖啡持机",
        "是否启用": "启用",
        "权重": 76,
        "适用品类": ["手机链"],
        "适用平台": ["得物", "小红书"],
        "使用频次": 0,
        "人物类型": "真人出镜",
        "年龄段": "22-28岁",
        "性别倾向": "女性",
        "外貌风格": "自然通勤妆，状态清爽",
        "姿态倾向": "自然站立/等车",
        "场景类型": "交通·地铁",
        "时段光境": "白天",
        "空间感": "室内公共空间",
        "光源类型": "室内灯光（地铁）",
        "光线方向": "漫射·无明显方向",
        "色温": "中性(4000-5000K)",
        "景别": "中景",
        "拍摄角度": "平视/略侧",
        "景深感": "浅景深·环境虚化",
        "镜头感": "35mm广角生活感",
        "场景基底_英文": "young woman on metro platform holding coffee in one hand and phone with chain in the other, realistic commute moment, clean station background, urban daily routine",
        "风格基调词": "地铁通勤,随手感,真实日常",
        "排除描述": "不要拥挤压迫感过强，不要链条被杯子完全挡住，不要地铁广告过分抢眼",
        "场景描述_中文": "女生在地铁站台等车，一手拿咖啡一手拿挂链手机，链条自然垂落，画面强调单手切换物品时的顺手感与真实通勤节奏。",
        "备注": "新增通勤次主场景。",
        "服装风格": "极简通勤或轻休闲通勤",
        "身体展示重点": "手部与半身站姿",
        "着装禁忌": "避免夸张运动装或礼服",
        "场景主题": "通勤",
        "氛围等级": "中",
        "道具建议": "咖啡杯、地铁卡、托特包",
        "光线风格标签": ["真实", "日常"],
        "适合人设标签": ["通勤", "松弛", "白领"],
        "差异化备注": "强调双手被占用时手机链的存在价值。",
    },
    {
        "场景编号": "SC106",
        "场景名称": "人物·周末市集边走边拍",
        "是否启用": "启用",
        "权重": 76,
        "适用品类": ["手机链"],
        "适用平台": ["得物", "小红书"],
        "使用频次": 0,
        "人物类型": "真人出镜",
        "年龄段": "22-28岁",
        "性别倾向": "女性",
        "外貌风格": "轻松自然妆感，周末出游状态",
        "姿态倾向": "自然站立/行走",
        "场景类型": "户外·城市",
        "时段光境": "午后",
        "空间感": "户外开放空间",
        "光源类型": "自然光",
        "光线方向": "侧光",
        "色温": "中性日光(5500K)",
        "景别": "中景带环境",
        "拍摄角度": "平视/跟拍",
        "景深感": "浅景深·街头虚化",
        "镜头感": "35mm广角视角",
        "场景基底_英文": "young woman walking through weekend market while holding phone with chain, casual citywalk outfit, stalls and people softly blurred, relaxed sunny lifestyle",
        "风格基调词": "市集,出游,citywalk",
        "排除描述": "不要摊位遮挡主体，不要游客感过重，不要链条完全隐身在衣服里",
        "场景描述_中文": "周末市集或街边活动中，女生边走边拍或看手机，挂链手机自然垂落，整体是轻松好逛又顺手的 citywalk 场景。",
        "备注": "新增周末出游 evergreen 场景。",
        "服装风格": "休闲街头或轻文艺",
        "身体展示重点": "全身到半身动态",
        "着装禁忌": "避免过度正式",
        "场景主题": "出游",
        "氛围等级": "中高",
        "道具建议": "饮品、帆布袋、太阳镜",
        "光线风格标签": ["生活感", "自然光"],
        "适合人设标签": ["文艺", "街头", "松弛"],
        "差异化备注": "强调流动感和轻出游过程。",
    },
    {
        "场景编号": "SC107",
        "场景名称": "人物·美术馆展览低饱和持机",
        "是否启用": "启用",
        "权重": 72,
        "适用品类": ["手机链"],
        "适用平台": ["得物", "小红书"],
        "使用频次": 0,
        "人物类型": "真人出镜",
        "年龄段": "22-28岁",
        "性别倾向": "女性",
        "外貌风格": "清冷干净，低饱和妆发",
        "姿态倾向": "自然站立/回头",
        "场景类型": "室内·工作室",
        "时段光境": "白天",
        "空间感": "室内公共空间",
        "光源类型": "柔光",
        "光线方向": "漫射·无明显方向",
        "色温": "中性白(5500K)",
        "景别": "中景带环境",
        "拍摄角度": "平视",
        "景深感": "中等景深",
        "镜头感": "50mm标准",
        "场景基底_英文": "young woman in minimal outfit at art gallery, holding phone with chain naturally, muted color palette, editorial but realistic exhibition atmosphere",
        "风格基调词": "展览,低饱和,清冷",
        "排除描述": "不要艺术装置喧宾夺主，不要游客照姿势，不要过度摆拍",
        "场景描述_中文": "低饱和展览空间里，女生自然驻足或回头，手机链与整体穿搭同框，画面偏干净克制，突出精致但不喧闹的出片感。",
        "备注": "新增差异化文艺场景。",
        "服装风格": "极简、中性色、文艺",
        "身体展示重点": "半身与回头动作",
        "着装禁忌": "避免高饱和杂色",
        "场景主题": "展览",
        "氛围等级": "中",
        "道具建议": "展览册、简约托特包",
        "光线风格标签": ["柔和", "低饱和"],
        "适合人设标签": ["文艺", "清冷", "中性简洁"],
        "差异化备注": "区别于咖啡馆，更偏静态高级感。",
    },
    {
        "场景编号": "SC108",
        "场景名称": "人物·夜间餐酒馆门口回头持机",
        "是否启用": "启用",
        "权重": 72,
        "适用品类": ["手机链"],
        "适用平台": ["得物", "小红书"],
        "使用频次": 0,
        "人物类型": "真人出镜",
        "年龄段": "22-28岁",
        "性别倾向": "女性",
        "外貌风格": "精致夜间妆感，微卷发或盘发",
        "姿态倾向": "回眸/侧身转动",
        "场景类型": "户外·夜间",
        "时段光境": "夜间",
        "空间感": "户外半开放空间",
        "光源类型": "霓虹灯/城市夜景光",
        "光线方向": "侧逆光",
        "色温": "混合色温·霓虹多彩",
        "景别": "中景/半身",
        "拍摄角度": "平视/略仰",
        "景深感": "浅景深·城市光斑虚化",
        "镜头感": "85mm人像感",
        "场景基底_英文": "young woman outside a wine bar at night, turning back while holding phone with chain, mixed warm neon reflections, refined date-night mood",
        "风格基调词": "夜间,约会,光泽",
        "排除描述": "不要酒吧元素过度成人化，不要背景人群混乱，不要链条被头发或包袋挡住",
        "场景描述_中文": "夜间餐酒馆或晚餐场景门口，女生侧身回头持挂链手机，链条在霓虹与暖灯混合光下带出精致金属光泽。",
        "备注": "新增夜间约会氛围场景。",
        "服装风格": "精致约会、小黑裙或轻礼服感",
        "身体展示重点": "肩颈线条与手部持机",
        "着装禁忌": "避免过分暴露或夜店化夸张妆造",
        "场景主题": "夜间约会",
        "氛围等级": "高",
        "道具建议": "小手包、高脚杯、门口灯牌",
        "光线风格标签": ["霓虹", "夜间"],
        "适合人设标签": ["精致", "甜酷", "夜景"],
        "差异化备注": "重点看低光金属质感。",
    },
    {
        "场景编号": "SC109",
        "场景名称": "人物·窗边晚餐前低头看机",
        "是否启用": "启用",
        "权重": 72,
        "适用品类": ["手机链"],
        "适用平台": ["得物", "小红书"],
        "使用频次": 0,
        "人物类型": "真人出镜",
        "年龄段": "22-28岁",
        "性别倾向": "女性",
        "外貌风格": "柔和妆感，精致但自然",
        "姿态倾向": "坐姿放松",
        "场景类型": "室内·餐厅",
        "时段光境": "傍晚",
        "空间感": "室内公共空间",
        "光源类型": "暖光",
        "光线方向": "侧光",
        "色温": "暖调(3200K)",
        "景别": "近景/半身",
        "拍摄角度": "平视/略俯",
        "景深感": "浅景深·环境虚化",
        "镜头感": "50mm标准",
        "场景基底_英文": "young woman seated by restaurant window before dinner, looking down at phone with chain, warm ambient light, intimate and polished evening scene",
        "风格基调词": "晚餐,温暖,精致",
        "排除描述": "不要桌面杂物太多，不要食物成为主体，不要链条淹没在桌布里",
        "场景描述_中文": "晚餐前坐在窗边或餐桌旁低头看手机，挂链手机自然落在手边或桌沿，整体是柔和、精致、能让链条成为造型细节的一幕。",
        "备注": "新增夜间室内约会场景。",
        "服装风格": "精致约会、针织或连衣裙",
        "身体展示重点": "手部、肩颈与坐姿线条",
        "着装禁忌": "避免办公风过重",
        "场景主题": "夜间约会",
        "氛围等级": "高",
        "道具建议": "餐具、烛台、小手包",
        "光线风格标签": ["暖调", "柔和"],
        "适合人设标签": ["精致", "甜酷", "约会"],
        "差异化备注": "比门口夜景更安静、更多室内细节。",
    },
    {
        "场景编号": "SC110",
        "场景名称": "人物·闺蜜咖啡馆并肩看手机",
        "是否启用": "启用",
        "权重": 72,
        "适用品类": ["手机链"],
        "适用平台": ["得物", "小红书"],
        "使用频次": 0,
        "人物类型": "真人出镜（双人）",
        "年龄段": "18-26岁",
        "性别倾向": "女性",
        "外貌风格": "青春自然妆感，双人风格协调但不完全复制",
        "姿态倾向": "坐姿放松",
        "场景类型": "室内·咖啡馆",
        "时段光境": "午后",
        "空间感": "室内公共空间",
        "光源类型": "自然光（窗边）",
        "光线方向": "侧光",
        "色温": "中性日光(5500K)",
        "景别": "中景带环境",
        "拍摄角度": "平视",
        "景深感": "浅景深·背景虚化",
        "镜头感": "35mm广角生活感",
        "场景基底_英文": "two young women at cafe table looking at their phones together, matching phone chains visible, bright window light, friendly and social atmosphere",
        "风格基调词": "闺蜜,同款,咖啡馆",
        "排除描述": "不要双人站位僵硬，不要其中一条链看不见，不要背景客人过度抢戏",
        "场景描述_中文": "两位女生在咖啡馆并肩或对坐看手机、互相分享内容，两条手机链同时出镜，画面强调社交关系感与同款氛围。",
        "备注": "新增双人社交场景。",
        "服装风格": "青春、甜酷或轻文艺双人协调穿搭",
        "身体展示重点": "双人上半身互动与手部",
        "着装禁忌": "避免两人风格完全割裂",
        "场景主题": "闺蜜同款",
        "氛围等级": "中高",
        "道具建议": "饮品、甜点、帆布包",
        "光线风格标签": ["社交", "自然光"],
        "适合人设标签": ["青春", "甜酷", "社交"],
        "差异化备注": "强调一起看手机而不是简单合照。",
    },
    {
        "场景编号": "SC111",
        "场景名称": "人物·闺蜜街头互拍同款持机",
        "是否启用": "启用",
        "权重": 72,
        "适用品类": ["手机链"],
        "适用平台": ["得物", "小红书"],
        "使用频次": 0,
        "人物类型": "真人出镜（双人）",
        "年龄段": "18-26岁",
        "性别倾向": "女性",
        "外貌风格": "青春街头感，妆容自然有精神",
        "姿态倾向": "自然站立/行走",
        "场景类型": "户外·街拍",
        "时段光境": "傍晚黄金时段",
        "空间感": "户外街道空间",
        "光源类型": "黄金时段自然光（逆光）",
        "光线方向": "侧逆光",
        "色温": "暖调(2800-3500K)",
        "景别": "中景/全身",
        "拍摄角度": "平视/跟拍",
        "景深感": "浅景深·街头虚化",
        "镜头感": "35mm广角",
        "场景基底_英文": "two stylish young women on city street taking photos of each other, matching phone chains visible, golden hour light, playful friendship energy",
        "风格基调词": "闺蜜,街头,黄金时段",
        "排除描述": "不要游客照感，不要两条链都被衣服遮挡，不要背景过于杂乱",
        "场景描述_中文": "傍晚街头两位女生互相拍照或边走边聊，两条手机链在动作里自然可见，画面有社交感、动态感和同款呼应。",
        "备注": "新增双人动态社交场景。",
        "服装风格": "街头休闲、甜酷双人搭配",
        "身体展示重点": "双人全身动态与手部持机",
        "着装禁忌": "避免极端夸张舞台装",
        "场景主题": "闺蜜同款",
        "氛围等级": "高",
        "道具建议": "相机、饮品、小包",
        "光线风格标签": ["黄金时段", "动态"],
        "适合人设标签": ["青春", "街头", "社交"],
        "差异化备注": "比室内闺蜜场景更动态、更适合首图。",
    },
]

SCENE_WEIGHT_UPDATES = {
    "SC029": 72,
    "SC030": 72,
    "SC031": 72,
    "SC032": 72,
    "SC033": 72,
    "SC034": 76,
    "SC035": 72,
    "SC036": 72,
    "SC037": 76,
    "SC038": 76,
    "SC072": 80,
    "SC073": 80,
    "SC074": 80,
}

PERSONAS = [
    {
        "人设编号": "PS017",
        "是否启用": "启用",
        "人设名称": "通勤效率感女生",
        "性别倾向": "女",
        "年龄段": "23-28",
        "外貌风格": "黑直发或低马尾，干净通勤妆，气质利落",
        "穿搭风格": "极简通勤、西装外套、衬衫或针织",
        "气质标签": ["通勤", "极简"],
        "动作倾向": "刷卡进楼、拿咖啡、边走边看手机",
        "适用品类": ["手机链", "通用"],
        "适用内容类型": ["通勤穿搭", "场景展示", "种草推荐"],
        "适合场景标签": ["通勤", "办公室", "电梯"],
        "Prompt描述模板": "Asian woman, 26 years old, efficient urban office styling, clean straight hair or low ponytail, minimal blazer or shirt outfit, calm capable expression, phone chain integrated into commute routine, modern professional energy",
        "一致性锚点模板": "同一女生，极简职场穿搭、低饱和配色、办公楼/电梯场景，相同面部轮廓与发型。",
        "优先级": 76,
        "备注": "新增手机链通勤人设。",
    },
    {
        "人设编号": "PS018",
        "是否启用": "启用",
        "人设名称": "周末 citywalk 女生",
        "性别倾向": "女",
        "年龄段": "22-27",
        "外貌风格": "自然轻妆，发型松弛，状态明亮",
        "穿搭风格": "休闲街头、轻文艺、周末出游搭配",
        "气质标签": ["松弛", "文艺"],
        "动作倾向": "边走边拍、拿饮品、回头看镜头",
        "适用品类": ["手机链", "通用"],
        "适用内容类型": ["出游记录", "场景展示", "种草推荐"],
        "适合场景标签": ["市集", "街头", "咖啡馆"],
        "Prompt描述模板": "Asian girl, 24 years old, relaxed weekend citywalk styling, natural makeup, soft loose hair, casual outfit with phone chain naturally visible, bright easygoing expression, lifestyle snapshot feeling",
        "一致性锚点模板": "同一女生，周末休闲穿搭、citywalk 场景、自然松弛状态，相同面部特征与发型。",
        "优先级": 76,
        "备注": "新增手机链轻出游人设。",
    },
    {
        "人设编号": "PS019",
        "是否启用": "启用",
        "人设名称": "夜间约会精致女生",
        "性别倾向": "女",
        "年龄段": "22-27",
        "外貌风格": "微卷发、精致妆容、夜间光感友好",
        "穿搭风格": "小黑裙、修身针织或轻礼服感穿搭",
        "气质标签": ["精致", "甜酷"],
        "动作倾向": "侧身回头、低头看手机、优雅坐姿",
        "适用品类": ["手机链"],
        "适用内容类型": ["约会穿搭", "场景展示", "好物分享"],
        "适合场景标签": ["夜景", "餐厅", "约会"],
        "Prompt描述模板": "Asian woman, 25 years old, refined evening date styling, softly curled hair, elegant fitted outfit, warm and confident expression, phone chain catching light in night setting, polished feminine mood",
        "一致性锚点模板": "同一女生，夜间精致穿搭、暖光或霓虹场景、稳定面部特征与卷发造型。",
        "优先级": 72,
        "备注": "新增手机链夜间约会人设。",
    },
    {
        "人设编号": "PS020",
        "是否启用": "启用",
        "人设名称": "闺蜜同款活力女生",
        "性别倾向": "女",
        "年龄段": "18-24",
        "外貌风格": "青春妆感，活泼自然，笑容松弛",
        "穿搭风格": "甜酷休闲或学院街头",
        "气质标签": ["青春", "社交"],
        "动作倾向": "并肩走动、互拍、一起看手机",
        "适用品类": ["手机链"],
        "适用内容类型": ["闺蜜同款", "种草推荐", "场景展示"],
        "适合场景标签": ["咖啡馆", "街头", "商场"],
        "Prompt描述模板": "Asian girl, 22 years old, lively social vibe, sweet-cool casual styling, bright smile, friendship-oriented energy, phone chain visible in playful daily interactions, youthful and outgoing expression",
        "一致性锚点模板": "同一女生，青春甜酷穿搭、闺蜜互动场景、笑容自然，相同面部轮廓与发型。",
        "优先级": 72,
        "备注": "新增手机链双人社交向人设。",
    },
]


def build_plans() -> list[SyncPlan]:
    return [
        SyncPlan("strategy", STRATEGIES, {code: {"优先级": value} for code, value in STRATEGY_PRIORITY_UPDATES.items()}),
        SyncPlan("shotplan", SHOTPLANS, {}),
        SyncPlan("scene", SCENES, {code: {"权重": value} for code, value in SCENE_WEIGHT_UPDATES.items()}),
        SyncPlan("persona", PERSONAS, {}),
    ]


def get_client() -> FeishuClient:
    cfg = load_system()
    fei = cfg["feishu"]
    return FeishuClient(app_id=fei["app_id"], app_secret=fei["app_secret"], base_token=fei["base_token"])


def index_records(fc: FeishuClient, table_key: str) -> dict[str, dict[str, Any]]:
    meta = TABLES[table_key]
    records = fc.list_records(meta["id"])
    indexed: dict[str, dict[str, Any]] = {}
    for record in records:
        fields = record.get("fields", {})
        code = fields.get(meta["code"])
        if code:
            indexed[str(code)] = record
    return indexed


def sync_table(fc: FeishuClient, plan: SyncPlan, apply: bool) -> dict[str, Any]:
    meta = TABLES[plan.table_key]
    indexed = index_records(fc, plan.table_key)
    summary = {"table": plan.table_key, "create": 0, "update": 0, "unchanged": 0, "created_codes": [], "updated_codes": [], "unchanged_codes": []}

    for payload in plan.create_or_update:
        code = str(payload[meta["code"]])
        existing = indexed.get(code)
        if existing is None:
            summary["create"] += 1
            summary["created_codes"].append(code)
            if apply:
                record_id = fc.create_record(meta["id"], payload)
                indexed[code] = {"record_id": record_id, "fields": payload}
            continue
        current_fields = existing.get("fields", {})
        delta = {k: v for k, v in payload.items() if current_fields.get(k) != v}
        if delta:
            summary["update"] += 1
            summary["updated_codes"].append(code)
            if apply:
                fc.update_record(meta["id"], existing["record_id"], delta)
        else:
            summary["unchanged"] += 1
            summary["unchanged_codes"].append(code)

    for code, updates in plan.updates_by_code.items():
        existing = indexed.get(code)
        if existing is None:
            continue
        current_fields = existing.get("fields", {})
        delta = {k: v for k, v in updates.items() if current_fields.get(k) != v}
        if delta:
            summary["update"] += 1
            summary["updated_codes"].append(code)
            if apply:
                fc.update_record(meta["id"], existing["record_id"], delta)
        else:
            summary["unchanged"] += 1
            summary["unchanged_codes"].append(code)

    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write to Feishu live tables")
    args = parser.parse_args()

    fc = get_client()
    results = []
    for plan in build_plans():
        results.append(sync_table(fc, plan, apply=args.apply))

    print(json.dumps({"mode": "apply" if args.apply else "dry-run", "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
