import { useL } from '../locales/LanguageContext';

export default function Footer() {
  const { lang } = useL();
  return (
    <footer className="site-footer">
      <div className="container">
        <div className="footer-inner">
          <div className="footer-brand">
            <span className="footer-brand-dot" />
            Open Gojira
          </div>
          <div className="footer-copy">
            © {new Date().getFullYear()} — {lang.footer.tagline}
          </div>
          <ul className="footer-links">
            <li><a href="https://github.com/iannil/open-gojira" target="_blank" rel="noopener noreferrer" className="footer-link">GitHub</a></li>
            <li><a href="mailto:hi@opengojira.com" className="footer-link">{lang.footer.contact}</a></li>
          </ul>
        </div>
      </div>
    </footer>
  );
}
