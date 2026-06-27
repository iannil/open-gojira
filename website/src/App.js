import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useEffect, useState } from 'react';
import { LangProvider, useL } from './locales/LanguageContext';
import Hero from './components/Hero';
import About from './components/About';
import DualEngine from './components/DualEngine';
import Pipeline from './components/Pipeline';
import TechStack from './components/TechStack';
import FAQ from './components/FAQ';
import Footer from './components/Footer';
function Nav() {
    const { lang, locale, toggle } = useL();
    const [scrolled, setScrolled] = useState(false);
    useEffect(() => {
        const onScroll = () => setScrolled(window.scrollY > 60);
        window.addEventListener('scroll', onScroll, { passive: true });
        return () => window.removeEventListener('scroll', onScroll);
    }, []);
    const scrollTo = (id) => {
        document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });
    };
    return (_jsxs("nav", { className: `site-nav ${scrolled ? 'scrolled' : ''}`, children: [_jsxs("div", { className: "nav-brand", children: [_jsx("span", { className: "nav-brand-name", children: "Open Gojira" }), _jsx("span", { className: "nav-brand-dot" })] }), _jsxs("ul", { className: "nav-links", children: [_jsx("li", { children: _jsx("button", { className: "nav-link", onClick: () => scrollTo('about'), children: lang.nav.about }) }), _jsx("li", { children: _jsx("button", { className: "nav-link", onClick: () => scrollTo('engines'), children: lang.nav.engines }) }), _jsx("li", { children: _jsx("button", { className: "nav-link", onClick: () => scrollTo('pipeline'), children: lang.nav.pipeline }) }), _jsx("li", { children: _jsx("button", { className: "nav-link", onClick: () => scrollTo('tech'), children: lang.nav.tech }) }), _jsx("li", { children: _jsx("button", { className: "nav-link", onClick: () => scrollTo('faq'), children: lang.nav.faq }) }), _jsx("li", { children: _jsx("button", { className: "nav-link lang-toggle", onClick: toggle, "aria-label": "Switch language", children: locale === 'zh' ? 'EN' : '中' }) }), _jsx("li", { children: _jsx("a", { href: "https://github.com/iannil/open-gojira", className: "nav-cta", target: "_blank", rel: "noopener noreferrer", children: lang.nav.cta }) })] })] }));
}
function CTABanner() {
    const { lang } = useL();
    const c = lang.ctaBanner;
    return (_jsxs("div", { className: "cta-banner", children: [_jsx("h2", { className: "cta-banner-title", children: c.title }), _jsx("p", { className: "cta-banner-desc", children: c.desc }), _jsxs("a", { href: "https://github.com/iannil/open-gojira", className: "btn-primary", target: "_blank", rel: "noopener noreferrer", children: [c.cta, _jsx("span", { "aria-hidden": "true", children: "\u2192" })] })] }));
}
function AppContent() {
    return (_jsxs(_Fragment, { children: [_jsx(Nav, {}), _jsxs("main", { children: [_jsx(Hero, {}), _jsx(About, {}), _jsx(DualEngine, {}), _jsx(Pipeline, {}), _jsx(TechStack, {}), _jsx(FAQ, {}), _jsx(CTABanner, {})] }), _jsx(Footer, {})] }));
}
export default function App() {
    return (_jsx(LangProvider, { children: _jsx(AppContent, {}) }));
}
