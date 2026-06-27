import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useL } from '../locales/LanguageContext';
export default function Footer() {
    const { lang } = useL();
    return (_jsx("footer", { className: "site-footer", children: _jsx("div", { className: "container", children: _jsxs("div", { className: "footer-inner", children: [_jsxs("div", { className: "footer-brand", children: [_jsx("span", { className: "footer-brand-dot" }), "Open Gojira"] }), _jsxs("div", { className: "footer-copy", children: ["\u00A9 ", new Date().getFullYear(), " \u2014 ", lang.footer.tagline] }), _jsxs("ul", { className: "footer-links", children: [_jsx("li", { children: _jsx("a", { href: "https://github.com/iannil/open-gojira", target: "_blank", rel: "noopener noreferrer", className: "footer-link", children: "GitHub" }) }), _jsx("li", { children: _jsx("a", { href: "mailto:hi@opengojira.com", className: "footer-link", children: lang.footer.contact }) })] })] }) }) }));
}
