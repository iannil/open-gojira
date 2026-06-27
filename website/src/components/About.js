import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useRef } from 'react';
import { useL } from '../locales/LanguageContext';
function StatCard({ number, label }) {
    return (_jsxs("div", { className: "stat-card", children: [_jsx("div", { className: "stat-number", children: number }), _jsx("div", { className: "stat-label", children: label })] }));
}
export default function About() {
    const { lang } = useL();
    const a = lang.about;
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
    return (_jsx("section", { className: "section-light", id: "about", ref: ref, children: _jsx("div", { className: "container", children: _jsxs("div", { className: "about-grid", children: [_jsxs("div", { className: "about-text", children: [_jsx("span", { className: "section-label", style: { color: 'var(--gold-500)' }, children: a.label }), _jsxs("h2", { className: "section-title reveal", children: [a.title1, _jsx("br", {}), a.title2] }), _jsx("p", { className: "reveal", style: { transitionDelay: '0.1s' }, children: a.p1 }), _jsx("p", { className: "reveal", style: { transitionDelay: '0.2s' }, children: a.p2 })] }), _jsxs("div", { className: "about-stats reveal", style: { transitionDelay: '0.3s' }, children: [_jsx(StatCard, { number: "2", label: a.stat1 }), _jsx(StatCard, { number: "4", label: a.stat2 }), _jsx(StatCard, { number: "19", label: a.stat3 }), _jsx(StatCard, { number: "686+", label: a.stat4 })] })] }) }) }));
}
