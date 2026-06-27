import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useRef } from 'react';
import { useL } from '../locales/LanguageContext';
import { IconFastAPI, IconReact, IconPostgreSQL, IconLixinger, IconGLM, IconECharts, IconAntDesign, IconAPScheduler, } from './Icons';
const ICONS = [
    _jsx(IconFastAPI, { size: 28 }),
    _jsx(IconReact, { size: 28 }),
    _jsx(IconPostgreSQL, { size: 28 }),
    _jsx(IconLixinger, { size: 28 }),
    _jsx(IconGLM, { size: 28 }),
    _jsx(IconECharts, { size: 28 }),
    _jsx(IconAntDesign, { size: 28 }),
    _jsx(IconAPScheduler, { size: 28 }),
];
const NAMES = ['FastAPI', 'React 19', 'PostgreSQL', '理杏仁', 'Zhipu GLM', 'ECharts 6', 'Ant Design 6', 'APScheduler'];
export default function TechStack() {
    const { lang } = useL();
    const t = lang.tech;
    const ref = useRef(null);
    useEffect(() => {
        const el = ref.current;
        if (!el)
            return;
        const observer = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    el.querySelectorAll('.reveal').forEach((r) => r.classList.add('visible'));
                }
            });
        }, { threshold: 0.1 });
        observer.observe(el);
        return () => observer.disconnect();
    }, []);
    const roles = [t.r1, t.r2, t.r3, t.r4, t.r5, t.r6, t.r7, t.r8];
    return (_jsx("section", { className: "section-light", id: "tech", ref: ref, children: _jsxs("div", { className: "container", children: [_jsxs("div", { style: { textAlign: 'center', marginBottom: 16 }, children: [_jsx("span", { className: "section-label", style: { color: 'var(--gold-500)' }, children: t.label }), _jsx("h2", { className: "section-title reveal", children: t.title }), _jsx("p", { className: "section-desc reveal", style: { margin: '0 auto', transitionDelay: '0.1s' }, children: t.desc })] }), _jsx("div", { className: "tech-grid reveal", style: { transitionDelay: '0.2s' }, children: ICONS.map((icon, i) => (_jsxs("div", { className: "tech-card", children: [_jsx("div", { className: "tech-icon", style: { color: 'var(--gold-500)' }, children: icon }), _jsx("div", { className: "tech-name", children: NAMES[i] }), _jsx("div", { className: "tech-role", children: roles[i] })] }, NAMES[i]))) })] }) }));
}
