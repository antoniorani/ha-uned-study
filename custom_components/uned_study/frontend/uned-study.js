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

  async signAssetPath(rawPath) {
    if (!this.subjectId) {
      return null;
    }

    this._signedAssetCache ??= new Map();
    const safePath = rawPath
      .split("/")
      .map((part) => encodeURIComponent(part))
      .join("/");
    const apiPath =
      `/api/uned_study/assets/${encodeURIComponent(this.subjectId)}/${safePath}`;
    const cached = this._signedAssetCache.get(apiPath);
    if (cached && cached.expiresAt > Date.now()) {
      return cached.path;
    }

    const result = await this._hass.callWS({
      type: "auth/sign_path",
      path: apiPath,
      expires: 600,
    });
    if (!result?.path) {
      return null;
    }

    this._signedAssetCache.set(apiPath, {
      path: result.path,
      expiresAt: Date.now() + 540_000,
    });
    return result.path;
  }

  async prepareMarkdown(value = "") {
    let text = String(value);
    const assetPattern = /\]\(assets\/([^\s)]+)\)/g;
    const paths = [
      ...new Set(
        [...text.matchAll(assetPattern)].map((match) => match[1]),
      ),
    ];

    for (const rawPath of paths) {
      try {
        const signedPath = await this.signAssetPath(rawPath);
        if (!signedPath) {
          continue;
        }
        text = text.split(`](assets/${rawPath})`).join(`](${signedPath})`);
      } catch (error) {
        console.warn("UNED Study could not sign asset path", rawPath, error);
      }
    }
    return text;
  }

  md(value = "") {
    this._pendingMarkdown ??= new Map();
    this._markdownSequence = (this._markdownSequence || 0) + 1;
    const key = `md-${this._markdownSequence}`;
    this._pendingMarkdown.set(key, String(value));
    return `<ha-markdown class="markdown" data-md-key="${key}" breaks></ha-markdown>`;
  }

  hydrateMarkdown(markdown) {
    const apply = () => {
      this.querySelectorAll("ha-markdown[data-md-key]").forEach((element) => {
        const raw = markdown.get(element.dataset.mdKey) || "";
        this.prepareMarkdown(raw)
          .then((value) => {
            if (element.isConnected) {
              element.content = value;
            }
          })
          .catch((error) => {
            console.warn("UNED Study Markdown preparation failed", error);
            if (element.isConnected) {
              element.content = raw;
            }
          });
      });
    };
    if (customElements.get("ha-markdown")) {
      apply();
    } else {
      customElements.whenDefined("ha-markdown").then(apply);
    }
  }

  shell(body) {
    const markdown = this._pendingMarkdown || new Map();
    this._pendingMarkdown = new Map();
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
        .top { display:flex; align-items:center; gap:12px; margin-bottom:20px; flex-wrap:wrap; }
        .top h1 { margin:0; flex:1; min-width:180px; }
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
          font: inherit;
        }
        button[disabled] { opacity:.55; cursor:wait; }
        button.secondary {
          background:transparent; color:var(--primary-text-color);
          border:1px solid var(--divider-color);
        }
        .star { background:transparent; color:var(--warning-color); font-size:22px; padding:4px; }
        .mini { padding:5px 8px; min-width:34px; }
        .actions { display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
        .study-options { display:grid; gap:14px; max-width:620px; }
        label { display:grid; gap:6px; font-weight:500; }
        select {
          width:100%; box-sizing:border-box; padding:10px 12px;
          border-radius:10px; border:1px solid var(--divider-color);
          color:var(--primary-text-color); background:var(--card-background-color);
          font:inherit;
        }
        .muted { color:var(--secondary-text-color); }
        .small { font-size:.88rem; }
        .answers { display:grid; gap:10px; margin-top:18px; }
        .answers button { text-align:left; }
        .answers ha-markdown { pointer-events:none; }
        .rating { display:grid; grid-template-columns:repeat(4,1fr); gap:8px; margin-top:18px; }
        .error { border-left:4px solid var(--error-color); }
        .ok { border-left:4px solid var(--success-color, green); }
        .source { margin-bottom:16px; }
        .markdown { display:block; }
        .markdown img { max-width:100%; height:auto; }
        @media(max-width:600px) {
          .page { padding:14px; }
          .rating { grid-template-columns:repeat(2,1fr); }
        }
      </style>
      <div class="page">${body}</div>
    `;
    this.hydrateMarkdown(markdown);
  }

  renderLoading(message = "Cargando UNED Study…") {
    this.shell(`<div class="card">${this.escape(message)}</div>`);
  }

  renderError(error) {
    this.shell(`
      <div class="top">
        <h1>UNED Study</h1>
        <button class="secondary" id="back-dashboard">Volver</button>
      </div>
      <div class="card error"><strong>Error</strong><br>${this.escape(error)}</div>
    `);
    this.querySelector("#back-dashboard").onclick = () => this.loadDashboard();
  }

  async loadDashboard() {
    try {
      const [data, status] = await Promise.all([
        this.call("dashboard"),
        this.call("content_status"),
      ]);
      this.dashboard = data;
      this.contentStatus = status;

      const cards = data.subjects.length
        ? data.subjects.map((subject) => this.subjectCard(subject)).join("")
        : `
          <div class="card">
            <h2>No hay asignaturas</h2>
            <p class="muted">
              Todavía no hay un snapshot válido de asignaturas en la caché local.
              Un administrador puede sincronizar el repositorio configurado.
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

      const source = status.source || {};
      const sourceInfo = `
        <div class="card source">
          <div><strong>Contenido:</strong>
            ${this.escape(source.repository || "sin configurar")}
            @ ${this.escape(source.branch || "")}
          </div>
          <div class="muted small">
            ${source.last_sync
              ? `Última sincronización: ${this.escape(source.last_sync.synced_at)} · ${source.last_sync.subject_count} asignaturas`
              : "Todavía no hay una sincronización confirmada en esta ejecución."}
          </div>
          ${source.last_error
            ? `<div class="small" style="color:var(--error-color)">${this.escape(source.last_error)}</div>`
            : ""}
        </div>`;

      const syncButton = this._hass?.user?.is_admin
        ? `<button id="sync-content">Sincronizar GitHub</button>`
        : "";

      this.shell(`
        <div class="top">
          <h1>UNED Study</h1>
          ${syncButton}
          <button class="secondary" id="refresh">Actualizar</button>
        </div>
        ${sourceInfo}
        <div class="grid">${cards}</div>
        <div style="height:16px"></div>
        ${adminErrors}
      `);

      this.querySelector("#refresh").onclick = () => this.loadDashboard();
      const sync = this.querySelector("#sync-content");
      if (sync) {
        sync.onclick = () => this.syncContent(sync);
      }
      this.querySelectorAll("[data-favorite]").forEach((button) => {
        button.onclick = () => this.toggleFavorite(button.dataset.favorite);
      });
      this.querySelectorAll("[data-open]").forEach((button) => {
        button.onclick = () => this.openSubject(button.dataset.open);
      });
      this.querySelectorAll("[data-resume]").forEach((button) => {
        button.onclick = () => this.resume(button.dataset.resume);
      });
      this.querySelectorAll("[data-move]").forEach((button) => {
        button.onclick = () => this.moveFavorite(
          button.dataset.subject,
          Number(button.dataset.move),
        );
      });
    } catch (error) {
      this.renderError(error?.message || String(error));
    }
  }

  async syncContent(button) {
    const oldText = button.textContent;
    button.disabled = true;
    button.textContent = "Sincronizando…";
    try {
      await this.call("sync_content");
      await this.loadDashboard();
    } catch (error) {
      button.disabled = false;
      button.textContent = oldText;
      this.renderError(error?.message || String(error));
    }
  }

  modeLabel(mode) {
    return {
      adaptive: "Adaptativo",
      due: "Repaso vencido",
      errors: "Falladas",
      new: "Nuevas",
      important: "Importantes",
    }[mode] || mode;
  }

  subjectCard(subject) {
    const progress = subject.progress || {};
    const total = (progress.correct || 0) + (progress.incorrect || 0);
    const accuracy = total
      ? Math.round((100 * (progress.correct || 0)) / total)
      : 0;
    const active = subject.active_session;
    const favoriteControls = subject.favorite
      ? `
        <button class="secondary mini" data-move="-1"
          data-subject="${this.escape(subject.id)}" title="Subir favorito">↑</button>
        <button class="secondary mini" data-move="1"
          data-subject="${this.escape(subject.id)}" title="Bajar favorito">↓</button>
      `
      : "";

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
          <div class="actions">
            ${favoriteControls}
            <button class="star" data-favorite="${this.escape(subject.id)}"
              title="Favorito">${subject.favorite ? "★" : "☆"}</button>
          </div>
        </div>
        <p>
          Revisiones: <strong>${progress.reviews || 0}</strong>
          · Acierto: <strong>${accuracy}%</strong>
        </p>
        ${active ? `
          <p class="muted small">
            Sesión activa · ${this.escape(this.modeLabel(active.mode))}
            · ${active.answered_count} respondidas
          </p>
        ` : ""}
        <div class="actions">
          ${active
            ? `<button data-resume="${this.escape(active.session_id)}">Continuar</button>`
            : ""}
          <button class="${active ? "secondary" : ""}"
            data-open="${this.escape(subject.id)}">
            ${active ? "Opciones" : "Estudiar"}
          </button>
        </div>
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

  async moveFavorite(subjectId, delta) {
    const favorites = this.dashboard.subjects
      .filter((subject) => subject.favorite)
      .map((subject) => subject.id);
    const index = favorites.indexOf(subjectId);
    const target = index + delta;
    if (index < 0 || target < 0 || target >= favorites.length) {
      return;
    }
    [favorites[index], favorites[target]] = [
      favorites[target],
      favorites[index],
    ];
    await this.call("reorder_favorites", { subject_ids: favorites });
    await this.loadDashboard();
  }

  async openSubject(subjectId) {
    try {
      this.subjectId = subjectId;
      const subject = await this.call("subject", { subject_id: subjectId });
      this.subjectMeta = subject;
      const summary = this.dashboard?.subjects.find(
        (item) => item.id === subjectId,
      );
      const active = summary?.active_session || null;
      const topicOptions = subject.topics
        .map(
          (topic) => `
            <option value="${this.escape(topic.id)}">
              ${this.escape(topic.title)}
            </option>`,
        )
        .join("");

      this.shell(`
        <div class="top">
          <button class="secondary" id="back-dashboard">← Asignaturas</button>
          <h1>${this.escape(subject.title)}</h1>
        </div>
        ${active ? `
          <div class="card ok" style="margin-bottom:16px">
            <h2 style="margin-top:0">Sesión en curso</h2>
            <p>
              ${this.escape(this.modeLabel(active.mode))}
              · ${active.answered_count} respondidas
            </p>
            <button id="continue-session">Continuar sesión</button>
          </div>
        ` : ""}
        <div class="card">
          <h2 style="margin-top:0">Nueva sesión</h2>
          <div class="study-options">
            <label>
              Modo de estudio
              <select id="study-mode">
                <option value="adaptive">Adaptativo</option>
                <option value="due">Repaso vencido</option>
                <option value="errors">Falladas anteriormente</option>
                <option value="new">Solo nuevas</option>
                <option value="important">Importantes (4–5)</option>
              </select>
            </label>
            <label>
              Tema
              <select id="study-topic">
                <option value="">Todos los temas</option>
                ${topicOptions}
              </select>
            </label>
            <div class="muted small">
              Empezar una nueva sesión deja la anterior de esta asignatura
              en pausa, sin borrar ningún progreso.
            </div>
            <div><button id="start-session">Empezar</button></div>
          </div>
        </div>
      `);

      this.querySelector("#back-dashboard").onclick = () => this.loadDashboard();
      const continueButton = this.querySelector("#continue-session");
      if (continueButton) {
        continueButton.onclick = () => this.resume(active.session_id);
      }
      this.querySelector("#start-session").onclick = () => {
        const mode = this.querySelector("#study-mode").value;
        const topic = this.querySelector("#study-topic").value || null;
        this.start(subjectId, mode, topic);
      };
    } catch (error) {
      this.renderError(error?.message || String(error));
    }
  }

  async resume(sessionId) {
    try {
      const data = await this.call("resume_session", {
        session_id: sessionId,
      });
      this.subjectId = data.subject_id;
      this.sessionId = data.session_id;
      this.subjectType = data.subject_type;
      this.currentItem = data.item || null;
      this.itemStarted = performance.now();

      if (!data.item) {
        await this.nextItem();
      } else if (data.item.type === "test") {
        this.renderTest(data.item);
      } else {
        this.renderFlashcard(data.item, false);
      }
    } catch (error) {
      this.renderError(error?.message || String(error));
    }
  }

  async start(subjectId, mode = "adaptive", topic = null) {
    try {
      const payload = {
        subject_id: subjectId,
        mode,
      };
      if (topic) {
        payload.topic = topic;
      }
      const data = await this.call("start_session", payload);
      this.subjectId = subjectId;
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
        ${this.md(item.question_md)}
        <div class="answers">
          ${item.answers.map((answer) => `
            <button data-answer="${this.escape(answer.id)}">
              ${this.md(answer.text_md)}
            </button>`).join("")}
        </div>
      </div>
    `);
    this.querySelector("#back").onclick = () => this.openSubject(this.subjectId);
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
        ${this.md(item.explanation_md || "")}
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
        ${this.md(item.front_md)}
        ${revealed ? `
          <hr>
          ${this.md(item.back_md)}
          ${item.mnemonic_md ? this.md(item.mnemonic_md) : ""}
          <div class="rating">
            <button data-rate="again">Otra vez</button>
            <button data-rate="hard">Difícil</button>
            <button data-rate="good">Bien</button>
            <button data-rate="easy">Fácil</button>
          </div>
        ` : `
          ${item.hint_md ? `<div class="muted">${this.md(item.hint_md)}</div>` : ""}
          <button id="reveal">Mostrar respuesta</button>
        `}
      </div>
    `);
    this.querySelector("#back").onclick = () => this.openSubject(this.subjectId);
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
