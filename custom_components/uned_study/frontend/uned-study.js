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
    if (this._examTimer) {
      clearInterval(this._examTimer);
      this._examTimer = null;
    }
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
        .stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr)); gap:10px; }
        .stat {
          padding:12px; border:1px solid var(--divider-color);
          border-radius:10px; background:var(--primary-background-color);
        }
        .stat strong { display:block; font-size:1.25rem; margin-top:4px; }
        .topic-list { display:grid; gap:8px; margin-top:12px; }
        .topic-row {
          display:grid; grid-template-columns:minmax(0,1fr) auto;
          gap:10px; padding:8px 0; border-bottom:1px solid var(--divider-color);
        }
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
        .answers button.selected {
          outline:3px solid var(--accent-color, var(--primary-color));
          outline-offset:1px;
        }
        .exam-bar {
          display:flex; gap:12px; align-items:center; flex-wrap:wrap;
          justify-content:space-between; margin-bottom:16px;
        }
        .exam-clock { font-size:1.25rem; font-weight:700; font-variant-numeric:tabular-nums; }
        .review-answer {
          border-radius:8px; padding:8px 10px; margin:6px 0;
          border:1px solid var(--divider-color);
        }
        .review-answer.correct { border-left:4px solid var(--success-color, green); }
        .review-answer.wrong { border-left:4px solid var(--error-color); }
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
      this.querySelectorAll("[data-resume-exam]").forEach((button) => {
        button.onclick = () => this.resumeExam(button.dataset.resumeExam);
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
      exam: "Simulacro",
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
            ? (
              active.mode === "exam"
                ? `<button data-resume-exam="${this.escape(active.session_id)}">Continuar simulacro</button>`
                : `<button data-resume="${this.escape(active.session_id)}">Continuar</button>`
            )
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
      const [subject, dashboard] = await Promise.all([
        this.call("subject", { subject_id: subjectId }),
        this.call("dashboard"),
      ]);
      this.subjectMeta = subject;
      this.dashboard = dashboard;
      const summary = dashboard.subjects.find(
        (item) => item.id === subjectId,
      );
      const active = summary?.active_session || null;
      const statistics = subject.statistics || {};
      const overall = statistics.overall || {};
      const topicStatistics = new Map(
        (statistics.topics || []).map((topic) => [topic.id, topic]),
      );
      const accuracy = overall.accuracy == null
        ? "—"
        : `${Math.round(overall.accuracy * 100)}%`;
      const mastery = `${Math.round((overall.mastery || 0) * 100)}%`;

      const topicOptions = subject.topics
        .map((topic) => {
          const stats = topicStatistics.get(topic.id) || {};
          return `
            <option value="${this.escape(topic.id)}">
              ${this.escape(topic.title)}
              · ${stats.studied || 0}/${stats.total || 0}
              · ${stats.due || 0} vencidas
            </option>`;
        })
        .join("");

      const topicRows = subject.topics
        .map((topic) => {
          const stats = topicStatistics.get(topic.id) || {};
          const attempts = (stats.correct || 0) + (stats.incorrect || 0);
          const topicAccuracy = attempts
            ? `${Math.round(100 * (stats.correct || 0) / attempts)}%`
            : "—";
          return `
            <div class="topic-row">
              <span>${this.escape(topic.title)}</span>
              <span class="muted small">
                ${stats.studied || 0}/${stats.total || 0}
                · ${stats.due || 0} vencidas
                · ${topicAccuracy}
              </span>
            </div>`;
        })
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
            <button id="continue-session">${active.mode === "exam" ? "Continuar simulacro" : "Continuar sesión"}</button>
          </div>
        ` : ""}
        <div class="card" style="margin-bottom:16px">
          <h2 style="margin-top:0">Progreso</h2>
          <div class="stats">
            <div class="stat"><span class="muted small">Estudiadas</span><strong>${overall.studied || 0}/${overall.total || 0}</strong></div>
            <div class="stat"><span class="muted small">Nuevas</span><strong>${overall.new || 0}</strong></div>
            <div class="stat"><span class="muted small">Vencidas</span><strong>${overall.due || 0}</strong></div>
            <div class="stat"><span class="muted small">Acierto</span><strong>${accuracy}</strong></div>
            <div class="stat"><span class="muted small">Dominio</span><strong>${mastery}</strong></div>
          </div>
          <div class="topic-list">${topicRows}</div>
        </div>
        ${subject.type === "test" && (subject.exam?.questions || subject.item_count) ? `
          <div class="card" style="margin-bottom:16px">
            <h2 style="margin-top:0">Simulacro de examen</h2>
            <p class="muted">
              ${Math.min(subject.exam?.questions || subject.item_count, subject.item_count)} preguntas
              · ${subject.exam?.duration_minutes || 60} min
              · penalización por fallo: ${subject.exam?.wrong_answer_penalty || 0}
            </p>
            <p class="small muted">
              No se muestran correcciones hasta entregar. La selección usa
              la importancia académica, no tus fallos personales.
            </p>
            <button id="start-exam">Empezar simulacro</button>
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
        continueButton.onclick = () => (
          active.mode === "exam"
            ? this.resumeExam(active.session_id)
            : this.resume(active.session_id)
        );
      }
      const examButton = this.querySelector("#start-exam");
      if (examButton) {
        examButton.onclick = () => this.startExam(subjectId);
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

  async startExam(subjectId) {
    try {
      this.renderLoading("Preparando simulacro…");
      const state = await this.call("start_exam", {
        subject_id: subjectId,
      });
      this.subjectId = subjectId;
      this.sessionId = state.session_id;
      this.examState = state;
      await this.loadExamQuestion(state.current_index || 0);
    } catch (error) {
      this.renderError(error?.message || String(error));
    }
  }

  async resumeExam(sessionId) {
    try {
      this.renderLoading("Recuperando simulacro…");
      const state = await this.call("exam_state", {
        session_id: sessionId,
      });
      this.subjectId = state.subject_id;
      this.sessionId = sessionId;
      this.examState = state;
      if (state.state !== "active" || state.expired) {
        await this.finishExam(false);
        return;
      }
      await this.loadExamQuestion(state.current_index || 0);
    } catch (error) {
      this.renderError(error?.message || String(error));
    }
  }

  async loadExamQuestion(index) {
    try {
      const data = await this.call("exam_question", {
        session_id: this.sessionId,
        index,
      });
      this.examQuestion = data;
      if (!this.examState) {
        this.examState = {};
      }
      this.examState.current_index = data.index;
      this.examState.question_count = data.question_count;
      this.examState.expires_at = data.expires_at;
      this.renderExamQuestion(data);
    } catch (error) {
      this.renderError(error?.message || String(error));
    }
  }

  formatExamTime(milliseconds) {
    const seconds = Math.max(0, Math.ceil(milliseconds / 1000));
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const rest = seconds % 60;
    return hours
      ? `${hours}:${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`
      : `${minutes}:${String(rest).padStart(2, "0")}`;
  }

  startExamClock(expiresAt) {
    const tick = () => {
      const clock = this.querySelector("#exam-clock");
      if (!clock) {
        return;
      }
      const remaining = new Date(expiresAt).getTime() - Date.now();
      clock.textContent = this.formatExamTime(remaining);
      if (remaining <= 0) {
        clearInterval(this._examTimer);
        this._examTimer = null;
        this.finishExam(false);
      }
    };
    tick();
    this._examTimer = setInterval(tick, 1000);
  }

  renderExamQuestion(data) {
    const item = data.item;
    const index = data.index;
    const total = data.question_count;
    const selected = data.selected_answer;
    const answered = this.examState?.answered_count || 0;

    this.shell(`
      <div class="top">
        <button class="secondary" id="exit-exam">← Asignatura</button>
        <h1>Simulacro</h1>
      </div>
      <div class="exam-bar">
        <div>
          <strong>Pregunta ${index + 1} de ${total}</strong>
          <span class="muted"> · ${answered} respondidas</span>
        </div>
        <div class="exam-clock" id="exam-clock">--:--</div>
      </div>
      <div class="card">
        ${this.md(item.question_md)}
        <div class="answers">
          ${item.answers.map((answer) => `
            <button
              class="${selected === answer.id ? "selected" : ""}"
              data-exam-answer="${this.escape(answer.id)}">
              ${this.md(answer.text_md)}
            </button>
          `).join("")}
        </div>
      </div>
      <div class="actions" style="margin-top:16px">
        <button class="secondary" id="exam-prev" ${index === 0 ? "disabled" : ""}>← Anterior</button>
        <button class="secondary" id="exam-next" ${index >= total - 1 ? "disabled" : ""}>Siguiente →</button>
        <button id="finish-exam">Entregar examen</button>
      </div>
    `);

    this.querySelector("#exit-exam").onclick = () =>
      this.openSubject(this.subjectId);
    this.querySelectorAll("[data-exam-answer]").forEach((button) => {
      button.onclick = () => this.selectExamAnswer(
        item.id,
        button.dataset.examAnswer,
      );
    });
    this.querySelector("#exam-prev").onclick = () =>
      this.loadExamQuestion(index - 1);
    this.querySelector("#exam-next").onclick = () =>
      this.loadExamQuestion(index + 1);
    this.querySelector("#finish-exam").onclick = () =>
      this.finishExam(true);

    this.startExamClock(data.expires_at);
  }

  async selectExamAnswer(itemId, answerId) {
    try {
      const result = await this.call("exam_answer", {
        session_id: this.sessionId,
        item_id: itemId,
        answer_id: answerId,
      });
      this.examState.answered_count = result.answered_count;
      this.examQuestion.selected_answer = answerId;
      this.renderExamQuestion(this.examQuestion);
    } catch (error) {
      if (String(error?.message || error).toLowerCase().includes("expired")) {
        await this.finishExam(false);
        return;
      }
      this.renderError(error?.message || String(error));
    }
  }

  async finishExam(confirmFirst = true) {
    if (this._finishingExam) {
      return;
    }
    if (
      confirmFirst
      && !window.confirm("¿Entregar el simulacro y ver la corrección?")
    ) {
      return;
    }

    this._finishingExam = true;
    if (this._examTimer) {
      clearInterval(this._examTimer);
      this._examTimer = null;
    }

    try {
      this.renderLoading("Corrigiendo simulacro…");
      const result = await this.call("finish_exam", {
        session_id: this.sessionId,
      });
      this.renderExamResults(result);
    } catch (error) {
      this.renderError(error?.message || String(error));
    } finally {
      this._finishingExam = false;
    }
  }

  renderExamResults(result) {
    const score = result.score || {};
    const grade = Number(score.grade_10 || 0).toFixed(2);
    const percentage = Number(score.percentage || 0).toFixed(1);
    const review = (result.review || []).map((entry, index) => {
      const item = entry.item;
      const selected = entry.answer_id;
      const answerRows = item.answers.map((answer) => {
        let cls = "";
        let suffix = "";
        if (answer.id === item.correct_answer) {
          cls = "correct";
          suffix = " ✓ correcta";
        } else if (answer.id === selected) {
          cls = "wrong";
          suffix = " ✗ tu respuesta";
        }
        return `
          <div class="review-answer ${cls}">
            ${this.md(answer.text_md)}
            ${suffix ? `<span class="small muted">${this.escape(suffix)}</span>` : ""}
          </div>`;
      }).join("");

      const state = entry.correct === true
        ? "Correcta"
        : entry.correct === false
          ? "Incorrecta"
          : "En blanco";
      return `
        <div class="card" style="margin-top:12px">
          <div class="muted small">Pregunta ${index + 1} · ${state}</div>
          ${this.md(item.question_md)}
          ${answerRows}
          ${item.explanation_md
            ? `<hr>${this.md(item.explanation_md)}`
            : ""}
        </div>`;
    }).join("");

    this.shell(`
      <div class="top">
        <h1>Resultado del simulacro</h1>
      </div>
      <div class="card">
        <div class="stats">
          <div class="stat"><span class="muted small">Nota /10</span><strong>${grade}</strong></div>
          <div class="stat"><span class="muted small">Puntuación</span><strong>${percentage}%</strong></div>
          <div class="stat"><span class="muted small">Correctas</span><strong>${score.correct || 0}</strong></div>
          <div class="stat"><span class="muted small">Incorrectas</span><strong>${score.incorrect || 0}</strong></div>
          <div class="stat"><span class="muted small">En blanco</span><strong>${score.blank || 0}</strong></div>
        </div>
        <p class="muted small">
          Penalización por respuesta incorrecta: ${score.wrong_answer_penalty || 0}.
        </p>
        <div class="actions">
          <button id="exam-results-subject">Volver a la asignatura</button>
          <button class="secondary" id="exam-results-home">Asignaturas</button>
        </div>
      </div>
      ${review}
    `);

    this.querySelector("#exam-results-subject").onclick = () =>
      this.openSubject(this.subjectId);
    this.querySelector("#exam-results-home").onclick = () =>
      this.loadDashboard();
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
      if (data.complete) {
        this.renderSessionComplete(data.session || {});
        return;
      }
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

  renderSessionComplete(session) {
    const attempts =
      (session.correct_count || 0) + (session.incorrect_count || 0);
    const accuracy = attempts
      ? `${Math.round(100 * (session.correct_count || 0) / attempts)}%`
      : "—";
    this.shell(`
      <div class="top">
        <h1>Sesión completada</h1>
      </div>
      <div class="card ok">
        <h2 style="margin-top:0">No quedan elementos en este modo</h2>
        <div class="stats">
          <div class="stat">
            <span class="muted small">Respondidas</span>
            <strong>${session.answered_count || 0}</strong>
          </div>
          <div class="stat">
            <span class="muted small">Correctas</span>
            <strong>${session.correct_count || 0}</strong>
          </div>
          <div class="stat">
            <span class="muted small">Incorrectas</span>
            <strong>${session.incorrect_count || 0}</strong>
          </div>
          <div class="stat">
            <span class="muted small">Acierto</span>
            <strong>${accuracy}</strong>
          </div>
        </div>
        <div class="actions" style="margin-top:16px">
          <button id="subject-after-complete">Volver a la asignatura</button>
          <button class="secondary" id="home-after-complete">Asignaturas</button>
        </div>
      </div>
    `);
    this.querySelector("#subject-after-complete").onclick = () =>
      this.openSubject(this.subjectId);
    this.querySelector("#home-after-complete").onclick = () =>
      this.loadDashboard();
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
