import { useL } from '../locales/LanguageContext';

export default function Hero() {
  const { lang } = useL();
  const h = lang.hero;
  return (
    <section className="hero" id="hero">
      <div className="hero-wave" aria-hidden="true">
        <svg viewBox="0 0 1600 500" preserveAspectRatio="xMidYMid slice">
          <path className="hero-wave-path" d="M0,400 C160,400 160,200 320,200 C480,200 480,350 640,350 C800,350 800,150 960,150 C1120,150 1120,300 1280,300 C1440,300 1440,400 1600,400" />
          <path className="hero-wave-path-2" d="M0,300 C200,300 200,380 400,380 C600,380 600,160 800,160 C1000,160 1000,340 1200,340 C1400,340 1400,280 1600,280" />
        </svg>
      </div>

      <div className="hero-content">
        <div className="hero-badge">
          <span className="hero-badge-dot" />
          {h.badge}
        </div>

        <h1 className="hero-title">
          <span className="hero-title-accent">Open Gojira</span>
          <br />
          {h.subtitle}
        </h1>

        <p className="hero-sub">
          {h.desc1}<br className="hidden-mobile" />
          {h.desc2}
        </p>

        <div className="hero-actions">
          <a href="https://github.com/iannil/open-gojira" className="btn-primary" target="_blank" rel="noopener noreferrer">
            {h.cta}
            <span aria-hidden="true">→</span>
          </a>
          <a href="#about" className="btn-secondary">
            {h.learn}
          </a>
        </div>
      </div>

      <div className="hero-scroll-hint">
        <span>{h.scroll}</span>
        <div className="hero-scroll-line" />
      </div>
    </section>
  );
}
