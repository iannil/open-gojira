"""BusinessPattern model — invest docs 生意模式 (per-business-pattern context).

Maps to invest1/2/3 methodology:
- first_principle_variable: invest1 第二章 第一性原理 (each business has one core driver)
- power_tier_baseline: invest1 第二章 选择权理论 (选择权位阶 0-3, 谁决定选择谁)
- thesis_variables_json: invest1 第三章 论点变量
- lixinger_industries_json: auto-association from Stock.industry string
- source_ref: docs reference (e.g., "invest3 §12") for builtin patterns
- is_builtin: distinguish seeder-seeded vs user-created

Context-type, not decision-type: this table holds methodology templates, not
buy/sell decisions. Downstream consumers (UI / Review / future strategy_engine)
read these attributes; the human + Strategy rules make decisions.

注: 字段名 power_tier / power_tier_baseline 为内部稳定 ID (改字段需 alembic migration);
UI/文档统一使用"选择权理论 / 选择权位阶"文案 (2026-06-17 invest-alignment audit)。
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BusinessPattern(Base):
    """Investment business pattern (生意模式) — per-pattern methodology context.

    Example rows (seeded):
        name="煤化工"          first_principle_variable="煤油价差套利"
        name="电解铝"          first_principle_variable="电力成本套利"
        name="药店零售"        first_principle_variable="加盟店增速"
        name="银行"            first_principle_variable="股息 + 地域 + 现金流匹配"
    """

    __tablename__ = "business_patterns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    """生意模式名,如 '煤化工' / '电解铝' / '药店零售' / '银行'。"""

    theme_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("themes.id"), nullable=True, index=True
    )
    """归属的安全主线 (能源安全/粮食安全/金融安全/资源安全/...)。nullable 表示未归类。"""

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    """人工可读描述,补充 first_principle_variable 没说清的细节。"""

    first_principle_variable: Mapped[str | None] = mapped_column(Text, nullable=True)
    """invest1 第二章 第一性原理:该生意的核心变量(描述性标签,如 '煤油价差' / '数店面' / '电力套利')。"""

    power_tier_baseline: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    """invest1 第二章 选择权位阶基线 (字段名 power_tier_baseline 为内部 ID):
    0=0 层选择权 (被单向选择, 两头受气) / 1=1 层 (双向选择) /
    2=2 层 (对稀缺资源/核心技术的选择权) / 3=3 层 (对三方完全选择权, 定价权垄断)。
    可被 Stock.qiu_detail_json 覆盖。"""

    is_midstream: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    """G2 (invest3 §13): True = 该生意模式是中游加工(煤化工/电解铝)。
    plan_runner 对 is_midstream=True 且 Stock.is_cost_leader != True 的股票自动剔除。
    上游/下游/金融/公用均 False。"""

    thesis_variables_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    """JSON list[{name, unit, source: 'manual'|'lixinger', current_value, target_condition}] — 该生意模式的论点变量模板。从 thesis_variable_sync_service.THESIS_VARIABLE_TEMPLATES 迁移而来。"""

    lixinger_industries_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    """JSON list[str] — 该 pattern 覆盖的 Lixinger industry 字符串(如 ['煤炭开采'])。用于自动推断 Stock.business_pattern_id。"""

    source_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    """文档章节引用,如 'invest3 §12'。is_builtin=True 时强制非空(由 seeder 保证)。"""

    is_builtin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
    """True=seeder 启动时 upsert,builtin 核心字段 read-only;False=用户自建,完全可编辑。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, onupdate=func.now(), nullable=True
    )
