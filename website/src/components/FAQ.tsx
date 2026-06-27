import { useEffect, useRef, useState } from 'react';
import { useL } from '../locales/LanguageContext';

export default function FAQ() {
  const { lang } = useL();
  const f = lang.faq;
  const [openIdx, setOpenIdx] = useState<number | null>(null);
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
    <section className="section-dark" id="faq" ref={ref}>
      <div className="container">
        <div style={{ textAlign: 'center', marginBottom: 16 }}>
          <span className="section-label" style={{ color: 'var(--gold-400)' }}>
            {f.label}
          </span>
          <h2 className="section-title reveal">{f.title}</h2>
        </div>

        <div className="faq-list reveal" style={{ transitionDelay: '0.1s' }}>
          {f.items.map((faq, i) => (
            <div key={i} className={`faq-item ${openIdx === i ? 'open' : ''}`}>
              <button
                className="faq-question"
                onClick={() => setOpenIdx(openIdx === i ? null : i)}
                aria-expanded={openIdx === i}
              >
                <span>{faq.q}</span>
                <span className="faq-icon">+</span>
              </button>
              <div className="faq-answer">{faq.a}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
