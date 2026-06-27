import { useEffect, useRef } from 'react';
import { useL } from '../locales/LanguageContext';
import { IconValue, IconChokepoint } from './Icons';

function EngineCard({
  variant,
  icon,
  name,
  en,
  desc,
  tags,
  features,
}: {
  variant: 'gold' | 'teal';
  icon: React.ReactNode;
  name: string;
  en: string;
  desc: string;
  tags: string[];
  features: string[];
}) {
  return (
    <div className={`engine-card ${variant}`}>
      <div className={`engine-icon-wrap ${variant}`}>{icon}</div>
      <div className="engine-name">{name}</div>
      <div className={`engine-en ${variant}`}>{en}</div>
      <p className="engine-desc">{desc}</p>
      <div className="engine-tags">
        {tags.map((t) => (
          <span key={t} className={`engine-tag ${variant}`}>{t}</span>
        ))}
      </div>
      <ul style={{ marginTop: 16, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {features.map((f) => (
          <li key={f} style={{ fontSize: 13, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ color: variant === 'gold' ? 'var(--gold-500)' : 'var(--teal-400)' }}>▸</span>
            {f}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function DualEngine() {
  const { lang } = useL();
  const e = lang.engines;
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
    <section className="section-dark" id="engines" ref={ref}>
      <div className="container">
        <div style={{ textAlign: 'center', marginBottom: 16 }}>
          <span className="section-label" style={{ color: 'var(--gold-400)' }}>
            {e.label}
          </span>
          <h2 className="section-title reveal">{e.title}</h2>
          <p className="section-desc reveal" style={{ margin: '0 auto', transitionDelay: '0.1s' }}>
            {e.desc}
          </p>
        </div>

        <div className="engines">
          <div className="reveal" style={{ transitionDelay: '0.2s' }}>
            <EngineCard
              variant="gold"
              icon={<IconValue />}
              name={e.valueName}
              en={e.valueEn}
              desc={e.valueDesc}
              tags={e.valueTags}
              features={e.valueFeats}
            />
          </div>

          <div className="reveal" style={{ transitionDelay: '0.3s' }}>
            <EngineCard
              variant="teal"
              icon={<IconChokepoint />}
              name={e.chokeName}
              en={e.chokeEn}
              desc={e.chokeDesc}
              tags={e.chokeTags}
              features={e.chokeFeats}
            />
          </div>
        </div>
      </div>
    </section>
  );
}
