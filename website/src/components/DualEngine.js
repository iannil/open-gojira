import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useRef } from 'react';
import { useL } from '../locales/LanguageContext';
import { IconValue, IconChokepoint } from './Icons';
function EngineCard({ variant, icon, name, en, desc, tags, features, }) {
    return (_jsxs("div", { className: `engine-card ${variant}`, children: [_jsx("div", { className: `engine-icon-wrap ${variant}`, children: icon }), _jsx("div", { className: "engine-name", children: name }), _jsx("div", { className: `engine-en ${variant}`, children: en }), _jsx("p", { className: "engine-desc", children: desc }), _jsx("div", { className: "engine-tags", children: tags.map((t) => (_jsx("span", { className: `engine-tag ${variant}`, children: t }, t))) }), _jsx("ul", { style: { marginTop: 16, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 8 }, children: features.map((f) => (_jsxs("li", { style: { fontSize: 13, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 8 }, children: [_jsx("span", { style: { color: variant === 'gold' ? 'var(--gold-500)' : 'var(--teal-400)' }, children: "\u25B8" }), f] }, f))) })] }));
}
export default function DualEngine() {
    const { lang } = useL();
    const e = lang.engines;
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
    return (_jsx("section", { className: "section-dark", id: "engines", ref: ref, children: _jsxs("div", { className: "container", children: [_jsxs("div", { style: { textAlign: 'center', marginBottom: 16 }, children: [_jsx("span", { className: "section-label", style: { color: 'var(--gold-400)' }, children: e.label }), _jsx("h2", { className: "section-title reveal", children: e.title }), _jsx("p", { className: "section-desc reveal", style: { margin: '0 auto', transitionDelay: '0.1s' }, children: e.desc })] }), _jsxs("div", { className: "engines", children: [_jsx("div", { className: "reveal", style: { transitionDelay: '0.2s' }, children: _jsx(EngineCard, { variant: "gold", icon: _jsx(IconValue, {}), name: e.valueName, en: e.valueEn, desc: e.valueDesc, tags: e.valueTags, features: e.valueFeats }) }), _jsx("div", { className: "reveal", style: { transitionDelay: '0.3s' }, children: _jsx(EngineCard, { variant: "teal", icon: _jsx(IconChokepoint, {}), name: e.chokeName, en: e.chokeEn, desc: e.chokeDesc, tags: e.chokeTags, features: e.chokeFeats }) })] })] }) }));
}
