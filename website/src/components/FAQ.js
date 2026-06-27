import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useRef, useState } from 'react';
import { useL } from '../locales/LanguageContext';
export default function FAQ() {
    const { lang } = useL();
    const f = lang.faq;
    const [openIdx, setOpenIdx] = useState(null);
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
    return (_jsx("section", { className: "section-dark", id: "faq", ref: ref, children: _jsxs("div", { className: "container", children: [_jsxs("div", { style: { textAlign: 'center', marginBottom: 16 }, children: [_jsx("span", { className: "section-label", style: { color: 'var(--gold-400)' }, children: f.label }), _jsx("h2", { className: "section-title reveal", children: f.title })] }), _jsx("div", { className: "faq-list reveal", style: { transitionDelay: '0.1s' }, children: f.items.map((faq, i) => (_jsxs("div", { className: `faq-item ${openIdx === i ? 'open' : ''}`, children: [_jsxs("button", { className: "faq-question", onClick: () => setOpenIdx(openIdx === i ? null : i), "aria-expanded": openIdx === i, children: [_jsx("span", { children: faq.q }), _jsx("span", { className: "faq-icon", children: "+" })] }), _jsx("div", { className: "faq-answer", children: faq.a })] }, i))) })] }) }));
}
