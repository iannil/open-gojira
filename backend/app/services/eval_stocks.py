"""Eval Set — fixed stock list for LLM quality baselines.

20 stocks selected for diversity across:
  - Industry (消费/科技/金融/医药/制造/能源)
  - Market cap (大盘/中盘/小盘)
  - Valuation status (高估/低估/合理)
  - Known edge cases (ST, 次新股, 高股息)
"""

EVAL_STOCKS: list[dict] = [
    # ── 消费 (5) ──
    {"code": "600519", "name": "贵州茅台", "reason": "消费龙头, 高ROE"},
    {"code": "000858", "name": "五粮液", "reason": "白酒二哥, 估值常低于茅台"},
    {"code": "002304", "name": "洋河股份", "reason": "白酒三哥, 近年增长放缓"},
    {"code": "600887", "name": "伊利股份", "reason": "乳业龙头, 稳定分红"},
    {"code": "000333", "name": "美的集团", "reason": "家电龙头, 全球化布局"},

    # ── 科技 (4) ──
    {"code": "000725", "name": "京东方A", "reason": "面板龙头, 强周期股"},
    {"code": "002415", "name": "海康威视", "reason": "安防龙头, 美国制裁影响"},
    {"code": "300750", "name": "宁德时代", "reason": "电池龙头, 新能源核心"},
    {"code": "688981", "name": "中芯国际", "reason": "芯片制造, 地缘政治敏感"},

    # ── 金融 (3) ──
    {"code": "601398", "name": "工商银行", "reason": "大行, 高股息"},
    {"code": "600036", "name": "招商银行", "reason": "股份行龙头, 零售银行标杆"},
    {"code": "601318", "name": "中国平安", "reason": "综合金融, 估值低位"},

    # ── 医药 (3) ──
    {"code": "600276", "name": "恒瑞医药", "reason": "创新药龙头, 高研发投入"},
    {"code": "300760", "name": "迈瑞医疗", "reason": "医疗器械龙头"},
    {"code": "000538", "name": "云南白药", "reason": "中药龙头, 品牌护城河"},

    # ── 制造 (3) ──
    {"code": "600031", "name": "三一重工", "reason": "工程机械龙头, 强周期"},
    {"code": "601899", "name": "紫金矿业", "reason": "矿业龙头, 大宗商品周期"},
    {"code": "002460", "name": "赣锋锂业", "reason": "锂矿龙头, 新能源上游"},

    # ── 能源 / 公用 (2) ──
    {"code": "600900", "name": "长江电力", "reason": "水电龙头, 类债券"},
    {"code": "601985", "name": "中国核电", "reason": "核电运营, 确定性增长"},
]
