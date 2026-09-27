class UnedStudyPanel extends HTMLElement {
  set hass(value) {
    this._hass = value;
    if (!this._loaded) {
      this._loaded = true;
      this.loadDashboard();
    }
  }

  connectedCallback() {
    this.renderLoading();
  }

  call(type, data = {}) {
    return this._hass.callWS({ type: `uned_study/${type}`, ...data });
  }

  escape(value = "") {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  md(value = "") {
    let text = this.escape(value);
    text = text.replace(/^### (.*)$/gm, "<h3>$1</h3>");
    text = text.replace(/^## (.*)$/gm, "<h2>$1</h2>");
    text = text.replace(/^# (.*)$/gm, "<h1>$1</h1>");
    text = text.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    text = text.replace(/\*(.+?)\*/g, "<em>$1</em>");
    text = text.replace(/\`(.+?)\`/g, "<code>$1</code>");
    return text.replace(/\n/g, "<br>");
  }

  shell(body) {
    this.innerHTML = `
      <style>
        :host {
          display: block;
          min-height: 100%;
          background: var(--primary-background-color);
          color: var(--primary-text-color);
          font-family: var(--paper-font-body1_-_font-family, sans-serif);
        }
        .page { max-width: 1000px; margin: 0 auto; padding: 24px; }
        .top { display:flex; align-items:center; gap:12px; margin-bottom:20px; }
        .top h1 { margin:0; flex:1; }
        .grid { display:grid; gap:16px; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); }
        .card {
          background: var(--card-background-color);
          border-radius: var(--ha-card-border-radius, 12px);
          box-shadow: var(--ha-card-box-shadow);
          padding: 18px;
        }
        button {
          border:0; border-radius:10px; padding:10px 14px;
          cursor:pointer; background:var(--primary-color); color:white;
        }
        button.secondary {
          background:transparent; color:var(--primary-text-color);
          border:1px solid var(--divider-color);
        }
        .star { background:transparent; color:var(--warning-color); font-size:22px; padding:4px; }
        .muted { color:var(--secondary-text-color); }
        .answers { display:grid; gap:10px; margin-top:18px; }
        .answers button { text-align:left; }
        .rating { display:grid; grid-template-columns:repeat(4,1fr); gap:8px; margin-top:18px; }
        .error { border-left:4px solid var(--error-color); }
        .ok { border-left:4px solid var(--success-color, green); }
        .markdown table { border-collapse:collapse; }
        .markdown td,.markdown th { border:1px solid var(--divider-color); padding:6px; }
        @media(max-width:600px) {
          .page { padding:14px; }
          .rating { grid-template-columns:repeat(2,1fr); }
        }
      </style>
      <div class="page">${body}</div>
    `;
  }

  renderLoading() {
    this.shell("<div class='card'>Cargando UNED Study…</div>");
  }

  renderError(error) {
    this.shell(`
      <div class="top"><h1>UNED Study</h1></div>
      <div class="card error"><strong>Error</strong><br>${this.escape(error)}</div>
    `);
  }

  async loadDashboard() {
    try {
      const data = await this.call("dashboard");
      this.dashboard = data;
      const cards = data.subjects.length
        ? data.subjects.map((subject) => this.subjectCard(subject)).join("")
        : `
          <div class="card">
            <h2>No hay asignaturas</h2>
            <p class="muted">
              Añade subject.json a /config/uned_study/content/&lt;subject_id&gt;/
              y recarga el contenido.
            </p>
          </div>`;

      const adminErrors = Object.keys(data.content_errors || {}).length
        ? `<div class="card error">
             <h3>Errores de contenido</h3>
             ${Object.entries(data.content_errors)
               .map(([key, value]) => `<p><strong>${this.escape(key)}</strong>: ${this.escape(value)}</p>`)
               .join("")}
           </div>`
        : "";

      this.shell(`
        <div class="top">
          <h1>UNED Study</h1>
          <button class="secondary" id="refresh">Actualizar</button>
        </div>
        <div class="grid">${cards}</div>
        <div style="height:16px"></div>
        ${adminErrors}
      `);
      this.querySelector("#refresh").onclick = () => this.loadDashboard();
      this.querySelectorAll("[data-favorite]").forEach((button) => {
        button.onclick = () => this.toggleFavorite(button.dataset.favorite);
      });
      this.querySelectorAll("[data-study]").forEach((button) => {
        button.onclick = () => this.start(button.dataset.study);
      });
    } catch (error) {
      this.renderError(error?.message || String(error));
    }
  }

  subjectCard(subject) {
    const progress = subject.progress || {};
    const total = (progress.correct || 0) + (progress.incorrect || 0);
    const accuracy = total
      ? Math.round((100 * (progress.correct || 0)) / total)
      : 0;
    return `
      <div class="card">
        <div style="display:flex;align-items:start;gap:8px">
          <div style="flex:1">
            <h2 style="margin-top:0">${this.escape(subject.title)}</h2>
            <div class="muted">
              ${subject.type === "test" ? "Test" : "Tarjetas"}
              · ${subject.item_count} elementos
              · ${subject.topic_count} temas
            </div>
          </div>
          <button class="star" data-favorite="${this.escape(subject.id)}"
            title="Favorito">${subject.favorite ? "★" : "☆"}</button>
        </div>
        <p>
          Revisiones: <strong>${progress.reviews || 0}</strong>
          · Acierto: <strong>${accuracy}%</strong>
        </p>
        <button data-study="${this.escape(subject.id)}">Estudiar</button>
      </div>
    `;
  }

  async toggleFavorite(subjectId) {
    const subject = this.dashboard.subjects.find((item) => item.id === subjectId);
    await this.call("set_favorite", {
      subject_id: subjectId,
      favorite: !subject.favorite,
    });
    await this.loadDashboard();
  }

  async start(subjectId) {
    try {
      const data = await this.call("start_session", {
        subject_id: subjectId,
        mode: "adaptive",
      });
      this.sessionId = data.session_id;
      this.subjectType = data.subject_type;
      await this.nextItem();
    } catch (error) {
      this.renderError(error?.message || String(error));
    }
  }

  async nextItem() {
    try {
      const data = await this.call("next_item", {
        session_id: this.sessionId,
      });
      this.currentItem = data.item;
      this.itemStarted = performance.now();
      if (data.item.type === "test") {
        this.renderTest(data.item);
      } else {
        this.renderFlashcard(data.item, false);
      }
    } catch (error) {
      this.renderError(error?.message || String(error));
    }
  }

  renderTest(item) {
    this.shell(`
      <div class="top">
        <button class="secondary" id="back">← Asignaturas</button>
        <h1>Pregunta</h1>
      </div>
      <div class="card">
        <div class="muted">Importancia ${item.importance}/5</div>
        <div class="markdown">${this.md(item.question_md)}</div>
        <div class="answers">
          ${item.answers.map((answer) => `
            <button data-answer="${this.escape(answer.id)}">
              ${this.md(answer.text_md)}
            </button>`).join("")}
        </div>
      </div>
    `);
    this.querySelector("#back").onclick = () => this.loadDashboard();
    this.querySelectorAll("[data-answer]").forEach((button) => {
      button.onclick = () => this.submitAnswer(button.dataset.answer);
    });
  }

  async submitAnswer(answerId) {
    const elapsed = Math.round(performance.now() - this.itemStarted);
    const result = await this.call("submit_answer", {
      session_id: this.sessionId,
      item_id: this.currentItem.id,
      answer_id: answerId,
      request_id: crypto.randomUUID(),
      response_ms: elapsed,
    });
    const item = result.item;
    this.shell(`
      <div class="top"><h1>Resultado</h1></div>
      <div class="card ${result.correct ? "ok" : "error"}">
        <h2>${result.correct ? "Correcta" : "Incorrecta"}</h2>
        <div class="markdown">${this.md(item.explanation_md || "")}</div>
        <p class="muted">Próximo repaso: ${this.escape(result.next_review_at || "")}</p>
        <button id="next">Siguiente</button>
      </div>
    `);
    this.querySelector("#next").onclick = () => this.nextItem();
  }

  renderFlashcard(item, revealed) {
    this.shell(`
      <div class="top">
        <button class="secondary" id="back">← Asignaturas</button>
        <h1>Tarjeta</h1>
      </div>
      <div class="card">
        <div class="muted">Importancia ${item.importance}/5</div>
        <div class="markdown">${this.md(item.front_md)}</div>
        ${revealed ? `
          <hr>
          <div class="markdown">${this.md(item.back_md)}</div>
          ${item.mnemonic_md ? `<p class="markdown">${this.md(item.mnemonic_md)}</p>` : ""}
          <div class="rating">
            <button data-rate="again">Otra vez</button>
            <button data-rate="hard">Difícil</button>
            <button data-rate="good">Bien</button>
            <button data-rate="easy">Fácil</button>
          </div>
        ` : `
          ${item.hint_md ? `<p class="muted markdown">${this.md(item.hint_md)}</p>` : ""}
          <button id="reveal">Mostrar respuesta</button>
        `}
      </div>
    `);
    this.querySelector("#back").onclick = () => this.loadDashboard();
    if (!revealed) {
      this.querySelector("#reveal").onclick = () => this.renderFlashcard(item, true);
    } else {
      this.querySelectorAll("[data-rate]").forEach((button) => {
        button.onclick = () => this.rateCard(button.dataset.rate);
      });
    }
  }

  async rateCard(rating) {
    const elapsed = Math.round(performance.now() - this.itemStarted);
    await this.call("rate_card", {
      session_id: this.sessionId,
      item_id: this.currentItem.id,
      rating,
      request_id: crypto.randomUUID(),
      response_ms: elapsed,
    });
    await this.nextItem();
  }
}

customElements.define("uned-study-panel", UnedStudyPanel);
