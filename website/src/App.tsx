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

  const scrollTo = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <nav className={`site-nav ${scrolled ? 'scrolled' : ''}`}>
      <div className="nav-brand">
        <span className="nav-brand-name">Open Gojira</span>
        <span className="nav-brand-dot" />
      </div>
      <ul className="nav-links">
        <li><button className="nav-link" onClick={() => scrollTo('about')}>{lang.nav.about}</button></li>
        <li><button className="nav-link" onClick={() => scrollTo('engines')}>{lang.nav.engines}</button></li>
        <li><button className="nav-link" onClick={() => scrollTo('pipeline')}>{lang.nav.pipeline}</button></li>
        <li><button className="nav-link" onClick={() => scrollTo('tech')}>{lang.nav.tech}</button></li>
        <li><button className="nav-link" onClick={() => scrollTo('faq')}>{lang.nav.faq}</button></li>
        <li>
          <button className="nav-link lang-toggle" onClick={toggle} aria-label="Switch language">
            {locale === 'zh' ? 'EN' : '中'}
          </button>
        </li>
        <li>
          <a href="https://github.com/iannil/open-gojira" className="nav-cta" target="_blank" rel="noopener noreferrer">
            {lang.nav.cta}
          </a>
        </li>
      </ul>
    </nav>
  );
}

function CTABanner() {
  const { lang } = useL();
  const c = lang.ctaBanner;
  return (
    <div className="cta-banner">
      <h2 className="cta-banner-title">{c.title}</h2>
      <p className="cta-banner-desc">{c.desc}</p>
      <a href="https://github.com/iannil/open-gojira" className="btn-primary" target="_blank" rel="noopener noreferrer">
        {c.cta}
        <span aria-hidden="true">→</span>
      </a>
    </div>
  );
}

function AppContent() {
  return (
    <>
      <Nav />
      <main>
        <Hero />
        <About />
        <DualEngine />
        <Pipeline />
        <TechStack />
        <FAQ />
        <CTABanner />
      </main>
      <Footer />
    </>
  );
}

export default function App() {
  return (
    <LangProvider>
      <AppContent />
    </LangProvider>
  );
}
