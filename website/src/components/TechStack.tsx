import { useEffect, useRef } from 'react';
import { useL } from '../locales/LanguageContext';
import {
  IconFastAPI, IconReact, IconPostgreSQL, IconLixinger,
  IconGLM, IconECharts, IconAntDesign, IconAPScheduler,
} from './Icons';

const ICONS = [
  <IconFastAPI size={28} />, <IconReact size={28} />, <IconPostgreSQL size={28} />,
  <IconLixinger size={28} />, <IconGLM size={28} />, <IconECharts size={28} />,
  <IconAntDesign size={28} />, <IconAPScheduler size={28} />,
];

const NAMES = ['FastAPI', 'React 19', 'PostgreSQL', '理杏仁', 'Zhipu GLM', 'ECharts 6', 'Ant Design 6', 'APScheduler'];

export default function TechStack() {
  const { lang } = useL();
  const t = lang.tech;
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

  const roles = [t.r1, t.r2, t.r3, t.r4, t.r5, t.r6, t.r7, t.r8];

  return (
    <section className="section-light" id="tech" ref={ref}>
      <div className="container">
        <div style={{ textAlign: 'center', marginBottom: 16 }}>
          <span className="section-label" style={{ color: 'var(--gold-500)' }}>
            {t.label}
          </span>
          <h2 className="section-title reveal">{t.title}</h2>
          <p className="section-desc reveal" style={{ margin: '0 auto', transitionDelay: '0.1s' }}>
            {t.desc}
          </p>
        </div>

        <div className="tech-grid reveal" style={{ transitionDelay: '0.2s' }}>
          {ICONS.map((icon, i) => (
            <div key={NAMES[i]} className="tech-card">
              <div className="tech-icon" style={{ color: 'var(--gold-500)' }}>{icon}</div>
              <div className="tech-name">{NAMES[i]}</div>
              <div className="tech-role">{roles[i]}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
