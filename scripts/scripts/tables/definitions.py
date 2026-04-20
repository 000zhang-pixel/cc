"""
7 张飞书多维表格的字段定义。

字段类型码（飞书 Bitable API）：
  1    文本（多行文本）
  2    数字
  3    单选
  4    多选
  5    日期/日期时间
  17   附件
  18   单向关联
  19   查找引用
  22   评分
  1001 自动编号

关联字段（type=18）和查找引用字段（type=19）需要 target_table_id，
在建表完成后由 setup_base.py 根据表名解析注入，这里用 target_table 名称占位。

建表顺序按依赖关系排列，被关联的表先建。
"""

# ---------------------------------------------------------------------------
# 字段类型常量
# ---------------------------------------------------------------------------
TEXT = 1
NUMBER = 2
SINGLE = 3
MULTI = 4
DATE = 5
ATTACHMENT = 17
LINK = 18
LOOKUP = 19
RATING = 22
AUTO_NUMBER = 1001


def _opt(options: list[str]) -> dict:
    """生成单选/多选的 property.options 结构"""
    return {"options": [{"name": o} for o in options]}


# ---------------------------------------------------------------------------
# 表定义列表（按建表顺序排列）
# ---------------------------------------------------------------------------

TABLES: list[dict] = [

    # -----------------------------------------------------------------------
    # 表1 SKU信息表（无依赖）
    # -----------------------------------------------------------------------
    {
        "name": "SKU信息表",
        "fields": [
            {"field_name": "SKU编号",   "type": TEXT},
            {"field_name": "SKU名称",   "type": TEXT},
            {"field_name": "SPU编号",   "type": TEXT},
            {"field_name": "产品简称",  "type": TEXT},
            {"field_name": "商品名称",  "type": TEXT},
            {"field_name": "品类",      "type": SINGLE, "property": _opt(["手机壳", "手机挂架", "其他"])},
            {"field_name": "适配机型",  "type": TEXT},
            {"field_name": "材质",      "type": MULTI,  "property": _opt(["透明", "磨砂", "皮质", "硅胶", "金属"])},
            {"field_name": "颜色",      "type": MULTI,  "property": _opt(["透明", "黑", "白", "渐变", "彩色"])},
            {"field_name": "风格",      "type": MULTI,  "property": _opt(["简约", "潮流", "可爱", "商务", "复古"])},
            {"field_name": "目标人群",  "type": MULTI,  "property": _opt(["学生", "白领", "潮人", "商务人士"])},
            {"field_name": "卖点1",     "type": TEXT},
            {"field_name": "卖点2",     "type": TEXT},
            {"field_name": "卖点3",     "type": TEXT},
            {"field_name": "价格区间",  "type": NUMBER},
            {"field_name": "白底图",    "type": ATTACHMENT},
            {"field_name": "销售平台",  "type": MULTI,  "property": _opt(["得物", "小红书"])},
            {"field_name": "上架状态",  "type": SINGLE, "property": _opt(["待上架", "已上架", "下架"])},
        ],
        "links": [],
        "lookups": [],
    },

    # -----------------------------------------------------------------------
    # 表7 标签库（无依赖）
    # -----------------------------------------------------------------------
    {
        "name": "标签库",
        "fields": [
            {"field_name": "标签名称",     "type": TEXT},
            {"field_name": "平台",         "type": MULTI,  "property": _opt(["得物", "小红书"])},
            {"field_name": "行业",         "type": SINGLE, "property": _opt(["3C数码", "时尚", "生活", "其他"])},
            {"field_name": "品类",         "type": SINGLE, "property": _opt(["手机壳", "手机挂架", "通用"])},
            {"field_name": "话题热度",     "type": NUMBER},
            {"field_name": "权重评分",     "type": NUMBER},
            {"field_name": "使用频次",     "type": NUMBER},
            {"field_name": "是否启用",     "type": SINGLE, "property": _opt(["启用", "停用"])},
            {"field_name": "最后更新时间", "type": DATE},
            {"field_name": "备注",         "type": TEXT},
        ],
        "links": [],
        "lookups": [],
    },

    # -----------------------------------------------------------------------
    # 表6 素材知识库（无依赖）
    # -----------------------------------------------------------------------
    {
        "name": "素材知识库",
        "fields": [
            # 用户录入
            {"field_name": "素材链接",     "type": TEXT},
            {"field_name": "原始标题",     "type": TEXT},
            {"field_name": "原始正文",     "type": TEXT},
            {"field_name": "素材附件",     "type": ATTACHMENT},
            {"field_name": "点赞数",       "type": NUMBER},
            {"field_name": "收藏数",       "type": NUMBER},
            {"field_name": "触发分析",     "type": SINGLE, "property": _opt(["否", "是"])},
            # 中台自动识别
            {"field_name": "来源平台",     "type": SINGLE, "property": _opt(["得物", "小红书", "其他"])},
            {"field_name": "内容形态",     "type": SINGLE, "property": _opt(["单图文", "图文", "视频"])},
            {"field_name": "品类",         "type": SINGLE, "property": _opt(["手机壳", "手机挂架", "通用"])},
            {"field_name": "内容类型",     "type": SINGLE, "property": _opt([
                "产品展示", "使用场景", "穿搭搭配", "场景展示", "日常vlog",
                "开箱", "买家秀/晒单", "节日/活动限定", "新品发布", "选购攻略/使用教程",
                "产品对比", "其他",
            ])},
            # AI 分析结果
            {"field_name": "标题公式",     "type": TEXT},
            {"field_name": "正文结构",     "type": TEXT},
            {"field_name": "情绪触发点",   "type": MULTI,  "property": _opt(["焦虑", "共鸣", "惊喜", "认同", "好奇"])},
            {"field_name": "卖点提炼方式", "type": SINGLE, "property": _opt(["功能型", "场景型", "情感型"])},
            {"field_name": "构图风格",     "type": TEXT},
            {"field_name": "色调氛围",     "type": TEXT},
            {"field_name": "场景道具",     "type": TEXT},
            {"field_name": "标签组合策略", "type": TEXT},
            # 状态
            {"field_name": "分析状态",     "type": SINGLE, "property": _opt(["待分析", "分析中", "已完成", "分析失败"])},
            {"field_name": "已应用至引擎", "type": SINGLE, "property": _opt(["否", "是"])},
            {"field_name": "收录时间",     "type": DATE},
        ],
        "links": [],
        "lookups": [],
    },

    # -----------------------------------------------------------------------
    # 表2 内容规划表（关联表1）
    # -----------------------------------------------------------------------
    {
        "name": "内容规划表",
        "fields": [
            {"field_name": "任务名称",       "type": TEXT},
            {"field_name": "任务类型",       "type": SINGLE, "property": _opt(["AI全创作", "图片实拍+AI文案", "视频实拍+AI文案"])},
            {"field_name": "内容类型",       "type": MULTI,  "property": _opt([
                "产品展示", "使用场景", "穿搭搭配", "场景展示", "日常vlog",
                "开箱", "买家秀/晒单", "节日/活动限定", "新品发布", "选购攻略/使用教程",
                "产品对比", "其他",
            ])},
            {"field_name": "目标平台",       "type": MULTI,  "property": _opt(["得物", "小红书"])},
            {"field_name": "生成图文篇数",   "type": NUMBER},
            {"field_name": "每篇图片数",     "type": NUMBER},
            {"field_name": "生成视频篇数",   "type": NUMBER},
            {"field_name": "视频最短时长(秒)","type": NUMBER},
            {"field_name": "视频最长时长(秒)","type": NUMBER},
            {"field_name": "注入标签数(N)",  "type": NUMBER},
            {"field_name": "文案模型",       "type": SINGLE, "property": _opt(["GPT-4.1", "Kimi K2.5", "DeepSeek"])},
            {"field_name": "图片模型",       "type": SINGLE, "property": _opt(["Nanobanana 2", "gemini-3.1-flash-image-preview", "gemini-3-pro-image-preview"])},
            {"field_name": "视频模型",       "type": SINGLE, "property": _opt(["Veo 3"])},
            {"field_name": "确认执行",       "type": SINGLE, "property": _opt(["否", "是"])},
            {"field_name": "执行状态",       "type": SINGLE, "property": _opt(["待执行", "执行中", "完成", "失败"])},
            {"field_name": "创建时间",       "type": DATE},
            {"field_name": "任务完成时间",   "type": DATE},
            {"field_name": "任务日志",       "type": TEXT},
            {"field_name": "备注",           "type": TEXT},
        ],
        "links": [
            {"field_name": "关联SKU", "target_table": "SKU信息表"},
        ],
        "lookups": [],
    },

    # -----------------------------------------------------------------------
    # 表3 提示词生成表（关联表2、表1）
    # -----------------------------------------------------------------------
    {
        "name": "提示词生成表",
        "fields": [
            {"field_name": "组号",       "type": TEXT},
            {"field_name": "Prompt类型", "type": SINGLE, "property": _opt(["图文正文", "图片生成", "视频内容", "视频脚本"])},
            {"field_name": "总Prompt",   "type": TEXT},
            {"field_name": "子Prompt列表","type": TEXT},
            {"field_name": "版本号",     "type": NUMBER},
            {"field_name": "生成来源",   "type": SINGLE, "property": _opt(["AI自动生成", "人工编写", "素材库反推"])},
            {"field_name": "使用模型",   "type": TEXT},
            {"field_name": "状态",       "type": SINGLE, "property": _opt(["草稿", "已确认", "已使用", "已废弃"])},
            {"field_name": "质量评分",   "type": RATING},
            {"field_name": "生成时间",   "type": DATE},
            {"field_name": "备注",       "type": TEXT},
        ],
        "links": [
            {"field_name": "关联规划", "target_table": "内容规划表"},
            {"field_name": "关联SKU",  "target_table": "SKU信息表"},
        ],
        "lookups": [],
    },

    # -----------------------------------------------------------------------
    # 表4 内容生成表（关联表2、表1）
    # -----------------------------------------------------------------------
    {
        "name": "内容生成表",
        "fields": [
            {"field_name": "任务类型",       "type": SINGLE, "property": _opt(["AI全创作", "图片实拍+AI文案", "视频实拍+AI文案"])},
            {"field_name": "目标平台",       "type": SINGLE, "property": _opt(["得物", "小红书"])},
            {"field_name": "内容类型",       "type": SINGLE, "property": _opt([
                "产品展示", "使用场景", "穿搭搭配", "场景展示", "日常vlog",
                "开箱", "买家秀/晒单", "节日/活动限定", "新品发布", "选购攻略/使用教程",
                "产品对比", "其他",
            ])},
            {"field_name": "内容形态",       "type": SINGLE, "property": _opt(["单图文", "图文", "视频"])},
            {"field_name": "标题",           "type": TEXT},
            {"field_name": "正文",           "type": TEXT},
            {"field_name": "标签",           "type": TEXT},
            {"field_name": "生成图片",       "type": ATTACHMENT},
            {"field_name": "生成视频",       "type": ATTACHMENT},
            {"field_name": "素材文件夹路径", "type": TEXT},
            {"field_name": "是否需要搬迁素材","type": SINGLE, "property": _opt(["否", "是"])},
            {"field_name": "确认搬迁",       "type": SINGLE, "property": _opt(["否", "是"])},
            {"field_name": "搬迁状态",       "type": SINGLE, "property": _opt(["待搬迁", "搬迁中", "已完成", "搬迁失败"])},
            {"field_name": "生成状态",       "type": SINGLE, "property": _opt(["生成中", "已生成", "生成失败"])},
            {"field_name": "失败原因",       "type": TEXT},
            {"field_name": "审核状态",       "type": SINGLE, "property": _opt(["待审核", "已通过", "已拒绝"])},
            {"field_name": "审核备注",       "type": TEXT},
            {"field_name": "生成时间",       "type": DATE},
        ],
        "links": [
            {"field_name": "关联规划", "target_table": "内容规划表"},
            {"field_name": "关联SKU",  "target_table": "SKU信息表"},
        ],
        "lookups": [],
    },

    # -----------------------------------------------------------------------
    # 表8 内容策略表（无依赖）
    # -----------------------------------------------------------------------
    {
        "name": "内容策略表",
        "fields": [
            {"field_name": "策略编号",       "type": TEXT},
            {"field_name": "策略名称",       "type": TEXT},
            {"field_name": "切入角度",       "type": SINGLE, "property": _opt([
                "精致生活", "学生平价", "极限测评", "社交货币", "实用主义", "情感共鸣",
            ])},
            {"field_name": "情绪基调",       "type": SINGLE, "property": _opt([
                "松弛感", "兴奋感", "专业理性", "温暖亲密", "高冷极简", "活泼俏皮",
            ])},
            {"field_name": "表达方式",       "type": SINGLE, "property": _opt([
                "生活记录感种草", "干货测评", "朋友推荐", "场景故事", "对比揭秘", "教程攻略",
            ])},
            {"field_name": "系统提示词前缀", "type": TEXT},
            {"field_name": "文案叙事节点",   "type": TEXT},   # JSON 数组
            {"field_name": "适用内容类型",   "type": MULTI, "property": _opt([
                "种草推荐", "好物分享", "深度测评", "对比测评", "穿搭搭配",
                "场景展示", "日常vlog", "开箱", "买家秀/晒单", "节日/活动限定",
                "新品发布", "选购攻略/使用教程",
            ])},
            {"field_name": "适用平台",       "type": MULTI, "property": _opt(["小红书", "得物"])},
            {"field_name": "适用品类",       "type": MULTI, "property": _opt(["手机壳", "手机挂架", "充电宝"])},
            {"field_name": "是否启用",       "type": SINGLE, "property": _opt(["启用", "停用"])},
            {"field_name": "优先级",         "type": NUMBER},
            {"field_name": "备注",           "type": TEXT},
        ],
        "links": [],
        "lookups": [],
    },

    # -----------------------------------------------------------------------
    # 表9 拍摄方案表（无依赖）
    # -----------------------------------------------------------------------
    {
        "name": "拍摄方案表",
        "fields": [
            {"field_name": "方案编号",     "type": TEXT},
            {"field_name": "方案名称",     "type": TEXT},
            {"field_name": "适用内容形态", "type": MULTI, "property": _opt(["图片生成", "视频画面"])},
            {"field_name": "适用内容类型", "type": MULTI, "property": _opt([
                "种草推荐", "好物分享", "深度测评", "对比测评", "穿搭搭配",
                "场景展示", "日常vlog", "开箱", "买家秀/晒单", "节日/活动限定",
                "新品发布", "选购攻略/使用教程",
            ])},
            {"field_name": "适用品类",     "type": MULTI, "property": _opt(["手机壳", "手机挂架", "充电宝"])},
            {"field_name": "角色序列",     "type": TEXT},   # JSON 数组
            {"field_name": "节点数量",     "type": NUMBER},
            {"field_name": "是否启用",     "type": SINGLE, "property": _opt(["启用", "停用"])},
            {"field_name": "备注",         "type": TEXT},
        ],
        "links": [],
        "lookups": [],
    },

    # -----------------------------------------------------------------------
    # 表10 视觉场景表（无依赖）
    # -----------------------------------------------------------------------
    {
        "name": "视觉场景表",
        "fields": [
            {"field_name": "场景编号",      "type": TEXT},
            {"field_name": "场景名称",      "type": TEXT},
            {"field_name": "是否启用",      "type": SINGLE, "property": _opt(["启用", "停用"])},
            {"field_name": "权重",          "type": NUMBER},
            {"field_name": "适用品类",      "type": MULTI, "property": _opt(["手机壳", "手机挂架", "充电宝"])},
            {"field_name": "适用平台",      "type": MULTI, "property": _opt(["小红书", "得物"])},
            {"field_name": "使用频次",      "type": NUMBER},
            # 人物模块
            {"field_name": "人物类型",      "type": SINGLE, "property": _opt([
                "有人物·主体", "有人物·配角", "无人物·纯产品",
            ])},
            {"field_name": "年龄段",        "type": SINGLE, "property": _opt([
                "18-22岁学生", "23-28岁职场", "28-35岁轻熟", "不指定",
            ])},
            {"field_name": "性别倾向",      "type": SINGLE, "property": _opt(["女性", "男性", "不限"])},
            {"field_name": "外貌风格",      "type": SINGLE, "property": _opt([
                "清爽学院", "精致通勤", "潮流街头", "自然日系", "不指定",
            ])},
            {"field_name": "姿态倾向",      "type": SINGLE, "property": _opt([
                "自然放松", "动态活泼", "优雅从容", "专注操作",
            ])},
            # 环境模块
            {"field_name": "场景类型",      "type": SINGLE, "property": _opt([
                "室内·咖啡馆", "室内·家居", "室内·工作室",
                "户外·街拍", "户外·公园", "棚拍·纯净",
            ])},
            {"field_name": "时段光境",      "type": SINGLE, "property": _opt([
                "清晨", "午后", "傍晚黄金时段", "夜间", "不限",
            ])},
            {"field_name": "空间感",        "type": SINGLE, "property": _opt([
                "紧凑特写", "中景带环境", "宽景带氛围",
            ])},
            # 光线模块
            {"field_name": "光源类型",      "type": SINGLE, "property": _opt([
                "自然光", "柔光（人造漫射）", "混合光", "棚拍纯净光",
            ])},
            {"field_name": "光线方向",      "type": SINGLE, "property": _opt([
                "侧光", "逆光", "顺光", "漫射·无明显方向",
            ])},
            {"field_name": "色温",          "type": SINGLE, "property": _opt([
                "暖调(3200K)", "中性日光(5500K)", "冷调(7000K)",
            ])},
            # 构图模块
            {"field_name": "景别",          "type": SINGLE, "property": _opt([
                "特写", "近景", "中景", "全景",
            ])},
            {"field_name": "拍摄角度",      "type": SINGLE, "property": _opt([
                "俯拍约45°", "平视", "仰拍", "正俯（平铺）",
            ])},
            {"field_name": "景深感",        "type": SINGLE, "property": _opt([
                "浅景深·背景虚化", "中等景深", "深景深·全清晰",
            ])},
            {"field_name": "镜头感",        "type": SINGLE, "property": _opt([
                "85mm人像感", "50mm标准", "35mm广角生活感", "微距特写",
            ])},
            # NANOBANANA Prompt 核心块
            {"field_name": "场景基底_英文", "type": TEXT},
            {"field_name": "风格基调词",    "type": TEXT},
            {"field_name": "排除描述",      "type": TEXT},
            # 参考资料
            {"field_name": "场景描述_中文", "type": TEXT},
            {"field_name": "参考图",        "type": ATTACHMENT},
            {"field_name": "备注",          "type": TEXT},
        ],
        "links": [],
        "lookups": [],
    },

    # -----------------------------------------------------------------------
    # 表5 发布执行表（关联表4，引用字段从表4继承）
    # -----------------------------------------------------------------------
    {
        "name": "发布执行表",
        "fields": [
            {"field_name": "发布方式",   "type": SINGLE, "property": _opt(["待定", "立即发布", "定时发布"])},
            {"field_name": "计划发布时间","type": DATE},
            {"field_name": "发布状态",   "type": SINGLE, "property": _opt(["待发布", "发布中", "已发布", "发布失败"])},
            {"field_name": "实际发布时间","type": DATE},
            {"field_name": "发布链接",   "type": TEXT},
            {"field_name": "失败原因",   "type": TEXT},
            {"field_name": "备注",       "type": TEXT},
        ],
        "links": [
            {"field_name": "关联内容", "target_table": "内容生成表"},
        ],
        # 查找引用字段：从关联内容表继承字段
        # lookup_link_field 为本表的关联字段名，target_field 为目标表字段名
        "lookups": [
            {"field_name": "关联SKU(引用)",  "lookup_link_field": "关联内容", "target_field": "关联SKU"},
            {"field_name": "任务类型(引用)", "lookup_link_field": "关联内容", "target_field": "任务类型"},
            {"field_name": "内容形态(引用)", "lookup_link_field": "关联内容", "target_field": "内容形态"},
            {"field_name": "目标平台(引用)", "lookup_link_field": "关联内容", "target_field": "目标平台"},
        ],
    },
]
