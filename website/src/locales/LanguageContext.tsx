import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';

export type Locale = 'zh' | 'en';

const ZH = {
  hero: { badge: 'v2.0 — 全链路闭环', subtitle: '个人股票自动驾驶舱', desc1: '规则筛选 + LLM 深度研究 + 规则/人工审批', desc2: '选股 → 深研 → 草稿 → 持仓跟踪，全流程自动化', cta: '查看源码', learn: '了解更多', scroll: '向下滚动' },
  about: { label: '是什么', title1: '你的个人投资研究团队，', title2: '7×24 小时在线', p1: 'Open Gojira 不是另一个炒股软件。它是一台双引擎自动驾驶舱——同时运行价值投资和产业链卡点两套独立的选股逻辑，用 LLM 做深度研究，将结果转成可执行的买卖草稿，最终由你一键确认。', p2: '唯一不自动的是券商真实下单——决策权始终在你手中。', stat1: '独立选股引擎', stat2: '大师投资视角', stat3: '自动化任务管线', stat4: '测试用例覆盖' },
  engines: { label: '双引擎', title: '两条独立的选股来源，不互相裁决', desc: '同一张买卖决策上汇合——一个负责找对的公司，一个负责定好价格。', valueName: '价值复利引擎', valueEn: 'Value Compounding', valueDesc: '基于 AI Berkshire 四大师（段永平、巴菲特、芒格、李录）的价值投资框架，寻找拥有宽阔护城河、长期确定性的好生意。', valueTags: ['好生意', '宽护城河', '安全边际', '长期确定性'], valueFeats: ['四大师视角对抗研究', '三策略估值区间 (Aggressive/Steady/Conservative)', '8 红线否决机制', 'LLM 深度研究报告'], chokeName: '产业链卡点引擎', chokeEn: 'Chokepoint Hunter', chokeDesc: '基于 Serenity 产业链卡点方法论，追踪市场叙事→系统变化→产业链稀缺层→卡点公司，捕捉新兴成长主题。', chokeTags: ['主题狩猎', '稀缺度', '产业链位置', '新兴成长'], chokeFeats: ['搜索 25+ 信息来源交叉验证', '产业链热度与稀缺度量化评分', '主题扫描 Pipeline（周期性触发）', '与价值引擎汇合到同一张草稿'] },
  pipeline: { label: '工作流', title: '从选股到持仓，全自动化流水线', desc: '无人工干预的核心流程，始终可审计、可回溯。', s1t: '股票池', s1d: '全市场基础筛选，质量/估值/分红多维度过滤', s2t: '深度研究', s2d: '双引擎独立分析，LLM 四大师视角对抗 + 产业链卡点评分', s3t: '买卖草稿', s3d: '价格落入区间 + 论文健康 + 仓位空间 → 自动生成 Draft', s4t: '执行确认', s4d: 'T+1 可卖股数计算，实际成交价回填，人工 1-click 审批', s5t: '持仓跟踪', s5d: '论题周跑监控，信号驱动卖出触发，全程审计日志' },
  tech: { label: '技术栈', title: '生产级技术底座', desc: '从数据采集到投资决策，每一层都经过精心选型。', r1: '后端框架 (Python 3.14)', r2: '前端框架 (TypeScript)', r3: '持久化数据库', r4: '唯一 A 股数据源', r5: 'LLM + web_search', r6: '可视化图表', r7: 'UI 组件库', r8: '后台任务调度' },
  faq: { label: 'FAQ', title: '常见问题', items: [
    { q: 'Open Gojira 是免费的吗？', a: 'Open Gojira 是个人开源项目。你需要自己准备理杏仁 API Key（数据源）和 Zhipu API Key（LLM 服务），两者都有免费额度，个人使用成本极低。' },
    { q: 'Open Gojira 能自动帮我下单交易吗？', a: '不能。Open Gojira 的设计原则是「除券商真实下单外，全部自动」。系统会生成买卖草稿（Draft），你可以一键审批确认，但实际下单需要你手动在券商软件中执行。决策权始终在你手中。' },
    { q: 'Open Gojira 和普通炒股软件有什么不同？', a: '传统炒股软件提供信息（行情、数据、研报）让你自己决策；Open Gojira 提供的是判断——它像你雇了一个投资研究团队，24 小时不停地用双引擎扫描市场、写研究报告、生成买卖建议，你只需要做最后的 Yes/No。' },
    { q: '双引擎是什么？它们会打架吗？', a: 'Open Gojira 同时运行两套独立的选股逻辑：价值复利引擎（巴菲特/段永平等四大师视角）找好生意，产业链卡点引擎找新兴成长。它们不互相裁决——一个负责「选哪只」，一个负责「定价格和风险」，最终汇合到同一张买卖草稿上。' },
    { q: '支持哪些市场？', a: '当前只支持 A 股市场（沪深京三市），数据来源为理杏仁。港股和美股支持在 roadmap 中。' },
    { q: '如何部署 Open Gojira？', a: '项目提供 Docker Compose 配置，一条命令即可启动前后端 + 数据库。也支持本地开发模式。详见 GitHub README。' },
  ] },
  nav: { about: '是什么', engines: '双引擎', pipeline: '工作流', tech: '技术栈', faq: 'FAQ', cta: '查看源码' },
  ctaBanner: { title: '准备好了吗？', desc: '开箱即用的双引擎投资系统，让你的研究效率提升一个量级。', cta: '查看源码' },
  footer: { tagline: '个人股票自动驾驶舱', contact: '联系' },
};

const EN: typeof ZH = {
  hero: { badge: 'v2.0 — Full Pipeline Closed Loop', subtitle: 'Personal Stock Autopilot', desc1: 'Rules screening + LLM deep research + Human approval', desc2: 'Selection → Research → Drafts → Tracking, fully automated', cta: 'View Source', learn: 'Learn More', scroll: 'Scroll down' },
  about: { label: 'About', title1: 'Your personal investment', title2: 'research team, 24/7', p1: "Open Gojira is not another trading app. It's a dual-engine autopilot—running value investing and supply chain chokepoint analysis side by side, using LLM for deep research, turning results into actionable buy/sell drafts for your one-click confirmation.", p2: 'The only thing not automated is the actual broker order—the decision is always yours.', stat1: 'Independent Engines', stat2: 'Master Perspectives', stat3: 'Automated Pipelines', stat4: 'Test Cases' },
  engines: { label: 'Dual Engine', title: 'Two independent sourcing engines, no arbitration', desc: 'They converge on the same decision—one finds the right company, the other sets the right price.', valueName: 'Value Compounding Engine', valueEn: 'Value Compounding', valueDesc: 'Based on the AI Berkshire framework (Duan Yongping, Buffett, Munger, Li Lu), seeking businesses with wide moats and long-term certainty.', valueTags: ['Great Business', 'Wide Moat', 'Margin of Safety', 'Long-term Certainty'], valueFeats: ['Four-master adversarial research', 'Three-strategy valuation ranges', '8 red-line veto mechanism', 'LLM deep research reports'], chokeName: 'Chokepoint Hunter Engine', chokeEn: 'Chokepoint Hunter', chokeDesc: 'Based on the Serenity chokepoint methodology, tracking market narrative → systemic change → supply chain scarcity → chokepoint companies.', chokeTags: ['Theme Hunting', 'Scarcity', 'Supply Chain Position', 'Emerging Growth'], chokeFeats: ['25+ cross-verified sources', 'Quantified heat & scarcity scoring', 'Periodic theme scan pipeline', 'Converges with value engine into one draft'] },
  pipeline: { label: 'Pipeline', title: 'From stock selection to position tracking, fully automated', desc: 'Core process with zero manual intervention, always auditable.', s1t: 'Stock Pool', s1d: 'Market-wide screening: quality, valuation, dividends', s2t: 'Deep Research', s2d: 'Dual-engine analysis + LLM adversarial research', s3t: 'Trade Draft', s3d: 'Price range + thesis health + room → auto Draft', s4t: 'Execution', s4d: 'T+1 shares calc, price fill-back, 1-click approval', s5t: 'Position Tracking', s5d: 'Weekly thesis monitoring, signal-driven sell triggers' },
  tech: { label: 'Tech Stack', title: 'Production-grade foundation', desc: 'Every layer is carefully selected, from data to decisions.', r1: 'Backend (Python 3.14)', r2: 'Frontend (TypeScript)', r3: 'Database', r4: 'A-Share Data Source', r5: 'LLM + web_search', r6: 'Visualization', r7: 'UI Library', r8: 'Task Scheduling' },
  faq: { label: 'FAQ', title: 'Frequently Asked Questions', items: [
    { q: 'Is Open Gojira free?', a: "Open Gojira is a personal open-source project. You need your own Lixinger API Key (data) and Zhipu API Key (LLM). Both have free tiers, so personal usage cost is minimal." },
    { q: 'Can Open Gojira trade automatically?', a: 'No. The design principle is "everything automated except broker orders". Drafts are generated for your review—actual order placement is manual in your broker software.' },
    { q: 'How is Open Gojira different from trading apps?', a: 'Traditional apps provide data for you to decide. Open Gojira provides judgment—it\'s like hiring an investment team that scans the market 24/7 and generates suggestions. You just say Yes or No.' },
    { q: 'How do the two engines work together?', a: 'Open Gojira runs two independent sourcing logics: Value Compounding (Buffett/Duan Yongping etc.) finds great businesses; Chokepoint Hunter finds emerging growth. They converge into one draft without arbitrating each other.' },
    { q: 'Which markets are supported?', a: 'Currently A-shares only (Shanghai/Shenzhen/Beijing). HK and US stocks are on the roadmap.' },
    { q: 'How to deploy Open Gojira?', a: 'Docker Compose configuration included—one command starts frontend, backend, and database. Local dev mode also available. See GitHub README.' },
  ] },
  nav: { about: 'About', engines: 'Engines', pipeline: 'Pipeline', tech: 'Tech Stack', faq: 'FAQ', cta: 'View Source' },
  ctaBanner: { title: 'Ready to get started?', desc: 'An out-of-the-box dual-engine investment system to level up your research.', cta: 'View Source' },
  footer: { tagline: 'Personal Stock Autopilot', contact: 'Contact' },
};

const ALL = { zh: ZH, en: EN } as const;

type LangContextType = {
  locale: Locale;
  lang: typeof ZH;
  toggle: () => void;
};

const LangContext = createContext<LangContextType>({
  locale: 'zh',
  lang: ZH,
  toggle: () => {},
});

export function useL() {
  return useContext(LangContext);
}

export function LangProvider({ children }: { children: ReactNode }) {
  const [locale, setLocale] = useState<Locale>('zh');

  const toggle = useCallback(() => {
    setLocale((prev) => (prev === 'zh' ? 'en' : 'zh'));
  }, []);

  return (
    <LangContext.Provider value={{ locale, lang: ALL[locale], toggle }}>
      {children}
    </LangContext.Provider>
  );
}
