import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useRef } from 'react';
import { useL } from '../locales/LanguageContext';
import { IconPool, IconResearch, IconDraft, IconExecute, IconTrack } from './Icons';
export default function Pipeline() {
    const { lang } = useL();
    const p = lang.pipeline;
    const ref = useRef(null);
    const STEPS = [
        { num: '01', icon: _jsx(IconPool, {}), title: p.s1t, desc: p.s1d },
        { num: '02', icon: _jsx(IconResearch, {}), title: p.s2t, desc: p.s2d },
        { num: '03', icon: _jsx(IconDraft, {}), title: p.s3t, desc: p.s3d },
        { num: '04', icon: _jsx(IconExecute, {}), title: p.s4t, desc: p.s4d },
        { num: '05', icon: _jsx(IconTrack, {}), title: p.s5t, desc: p.s5d },
    ];
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
    return (_jsx("section", { className: "section-light", id: "pipeline", ref: ref, children: _jsxs("div", { className: "container", children: [_jsxs("div", { style: { textAlign: 'center', marginBottom: 16 }, children: [_jsx("span", { className: "section-label", style: { color: 'var(--gold-500)' }, children: p.label }), _jsx("h2", { className: "section-title reveal", children: p.title }), _jsx("p", { className: "section-desc reveal", style: { margin: '0 auto', transitionDelay: '0.1s' }, children: p.desc })] }), _jsx("div", { className: "pipeline reveal", style: { transitionDelay: '0.2s' }, children: STEPS.map((step, i) => (_jsxs("div", { className: "pipeline-step", children: [_jsx("span", { className: "pipeline-step-num", children: step.num }), _jsx("div", { className: "pipeline-step-icon", style: { color: 'var(--gold-500)' }, children: step.icon }), _jsx("div", { className: "pipeline-step-title", children: step.title }), _jsx("div", { className: "pipeline-step-desc", children: step.desc }), i < STEPS.length - 1 && (_jsx("span", { className: "pipeline-arrow", style: { display: 'block', position: 'absolute', right: -14, top: '50%', transform: 'translateY(-50%)', color: 'var(--warm-300)', fontSize: 18 }, children: "\u2192" }))] }, step.num))) })] }) }));
}
