import { useEffect, useRef } from 'react';
import { useL } from '../locales/LanguageContext';

function StatCard({ number, label }: { number: string; label: string }) {
  return (
    <div className="stat-card">
      <div className="stat-number">{number}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

export default function About() {
  const { lang } = useL();
  const a = lang.about;
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            el.querySelectorAll('.reveal').forEach((r) => r.classList.add('visible'));
          }
        });
      },
      { threshold: 0.1 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <section className="section-light" id="about" ref={ref}>
      <div className="container">
        <div className="about-grid">
          <div className="about-text">
            <span className="section-label" style={{ color: 'var(--gold-500)' }}>
              {a.label}
            </span>
            <h2 className="section-title reveal">
              {a.title1}<br />{a.title2}
            </h2>
            <p className="reveal" style={{ transitionDelay: '0.1s' }}>
              {a.p1}
            </p>
            <p className="reveal" style={{ transitionDelay: '0.2s' }}>
              {a.p2}
            </p>
          </div>

          <div className="about-stats reveal" style={{ transitionDelay: '0.3s' }}>
            <StatCard number="2" label={a.stat1} />
            <StatCard number="4" label={a.stat2} />
            <StatCard number="19" label={a.stat3} />
            <StatCard number="686+" label={a.stat4} />
          </div>
        </div>
      </div>
    </section>
  );
}
