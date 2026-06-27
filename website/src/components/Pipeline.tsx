import { useEffect, useRef } from 'react';
import { useL } from '../locales/LanguageContext';
import { IconPool, IconResearch, IconDraft, IconExecute, IconTrack } from './Icons';

export default function Pipeline() {
  const { lang } = useL();
  const p = lang.pipeline;
  const ref = useRef<HTMLElement>(null);

  const STEPS = [
    { num: '01', icon: <IconPool />, title: p.s1t, desc: p.s1d },
    { num: '02', icon: <IconResearch />, title: p.s2t, desc: p.s2d },
    { num: '03', icon: <IconDraft />, title: p.s3t, desc: p.s3d },
    { num: '04', icon: <IconExecute />, title: p.s4t, desc: p.s4d },
    { num: '05', icon: <IconTrack />, title: p.s5t, desc: p.s5d },
  ];

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
    <section className="section-light" id="pipeline" ref={ref}>
      <div className="container">
        <div style={{ textAlign: 'center', marginBottom: 16 }}>
          <span className="section-label" style={{ color: 'var(--gold-500)' }}>
            {p.label}
          </span>
          <h2 className="section-title reveal">{p.title}</h2>
          <p className="section-desc reveal" style={{ margin: '0 auto', transitionDelay: '0.1s' }}>
            {p.desc}
          </p>
        </div>

        <div className="pipeline reveal" style={{ transitionDelay: '0.2s' }}>
          {STEPS.map((step, i) => (
            <div key={step.num} className="pipeline-step">
              <span className="pipeline-step-num">{step.num}</span>
              <div className="pipeline-step-icon" style={{ color: 'var(--gold-500)' }}>{step.icon}</div>
              <div className="pipeline-step-title">{step.title}</div>
              <div className="pipeline-step-desc">{step.desc}</div>
              {i < STEPS.length - 1 && (
                <span className="pipeline-arrow" style={{ display: 'block', position: 'absolute', right: -14, top: '50%', transform: 'translateY(-50%)', color: 'var(--warm-300)', fontSize: 18 }}>→</span>
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
