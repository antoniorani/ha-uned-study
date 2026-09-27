(() => {
  "use strict";

  const root = document.getElementById("app");
  const basePath = window.location.pathname.endsWith("/")
    ? window.location.pathname
    : window.location.pathname + "/";

  const state = {
    dashboard: null,
    subjectId: null,
    sessionId: null,
    currentItem: null,
    exam: null,
    itemStarted: 0,
    examTimer: null,
  };

  function endpoint(path) {
    return basePath + String(path).replace(/^\/+/, "");
  }

  async function api(path, options = {}) {
    const init = {...options};
    init.headers = {...(options.headers || {})};
    if (options.body && typeof options.body !== "string") {
      init.body = JSON.stringify(options.body);
      init.headers["Content-Type"] = "application/json";
    }
    const response = await fetch(endpoint(path), init);
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `HTTP ${response.status}`);
    }
    return response.json();
  }

  function escapeHtml(value = "") {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function assetUrl(subjectId, raw) {
    const safe = String(raw)
      .split("/")
      .filter(Boolean)
      .map((part) => encodeURIComponent(part))
      .join("/");
    return endpoint(
      `api/assets/${encodeURIComponent(subjectId)}/${safe}`
    );
  }

  function inlineMarkdown(text, subjectId) {
    const tokens = [];
    let source = String(text || "");

    const token = (html) => {
      const key = `@@UNEDTOKEN${tokens.length}@@`;
      tokens.push(html);
      return key;
    };

    source = source.replace(
      /!\[([^\]]*)\]\(([^)]+)\)/g,
      (_match, alt, url) => {
        if (!subjectId || !String(url).startsWith("assets/")) {
          return escapeHtml(alt);
        }
        const src = assetUrl(subjectId, String(url).slice(7));
        return token(
          `<img src="${escapeHtml(src)}" alt="${escapeHtml(alt)}" loading="lazy">`
        );
      }
    );

    source = source.replace(
      /\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g,
      (_match, label, url) => token(
        `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}</a>`
      )
    );

    let html = escapeHtml(source);
    html = html.replace(/\`([^\`]+)\`/g, "<code>$1</code>");
    html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/\*([^*]+)\*/g, "<em>$1</em>");

    tokens.forEach((value, index) => {
      html = html.replace(`@@UNEDTOKEN${index}@@`, value);
    });
    return html;
  }

  function renderMarkdown(markdown, subjectId = state.subjectId) {
    const lines = String(markdown || "").replace(/\r/g, "").split("\n");
    const html = [];
    let index = 0;

    const isSeparator = (line) =>
      /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);

    while (index < lines.length) {
      const line = lines[index];

      if (!line.trim()) {
        index += 1;
        continue;
      }

      if (
        line.includes("|")
        && index + 1 < lines.length
        && isSeparator(lines[index + 1])
      ) {
        const headers = line
          .replace(/^\||\|$/g, "")
          .split("|")
          .map((cell) => cell.trim());
        index += 2;
        const rows = [];
        while (index < lines.length && lines[index].includes("|")) {
          rows.push(
            lines[index]
              .replace(/^\||\|$/g, "")
              .split("|")
              .map((cell) => cell.trim())
          );
          index += 1;
        }
        html.push("<table><thead><tr>");
        headers.forEach((cell) => {
          html.push(`<th>${inlineMarkdown(cell, subjectId)}</th>`);
        });
        html.push("</tr></thead><tbody>");
        rows.forEach((row) => {
          html.push("<tr>");
          row.forEach((cell) => {
            html.push(`<td>${inlineMarkdown(cell, subjectId)}</td>`);
          });
          html.push("</tr>");
        });
        html.push("</tbody></table>");
        continue;
      }

      const heading = line.match(/^(#{1,3})\s+(.+)$/);
      if (heading) {
        const level = heading[1].length;
        html.push(
          `<h${level}>${inlineMarkdown(heading[2], subjectId)}</h${level}>`
        );
        index += 1;
        continue;
      }

      if (/^>\s?/.test(line)) {
        const quote = [];
        while (index < lines.length && /^>\s?/.test(lines[index])) {
          quote.push(lines[index].replace(/^>\s?/, ""));
          index += 1;
        }
        html.push(
          `<blockquote>${quote.map((value) => inlineMarkdown(value, subjectId)).join("<br>")}</blockquote>`
        );
        continue;
      }

      if (/^\s*[-*]\s+/.test(line)) {
        const items = [];
        while (index < lines.length && /^\s*[-*]\s+/.test(lines[index])) {
          items.push(lines[index].replace(/^\s*[-*]\s+/, ""));
          index += 1;
        }
        html.push(
          `<ul>${items.map((value) => `<li>${inlineMarkdown(value, subjectId)}</li>`).join("")}</ul>`
        );
        continue;
      }

      if (/^\s*\d+\.\s+/.test(line)) {
        const items = [];
        while (index < lines.length && /^\s*\d+\.\s+/.test(lines[index])) {
          items.push(lines[index].replace(/^\s*\d+\.\s+/, ""));
          index += 1;
        }
        html.push(
          `<ol>${items.map((value) => `<li>${inlineMarkdown(value, subjectId)}</li>`).join("")}</ol>`
        );
        continue;
      }

      const paragraph = [line];
      index += 1;
      while (
        index < lines.length
        && lines[index].trim()
        && !/^(#{1,3})\s+/.test(lines[index])
        && !/^>\s?/.test(lines[index])
        && !/^\s*[-*]\s+/.test(lines[index])
        && !/^\s*\d+\.\s+/.test(lines[index])
      ) {
        paragraph.push(lines[index]);
        index += 1;
      }
      html.push(
        `<p>${paragraph.map((value) => inlineMarkdown(value, subjectId)).join("<br>")}</p>`
      );
    }

    return `<div class="markdown">${html.join("")}</div>`;
  }

  function clearExamTimer() {
    if (state.examTimer) {
      clearInterval(state.examTimer);
      state.examTimer = null;
    }
  }

  function shell(body, title = "UNED Study", back = null) {
    clearExamTimer();
    root.innerHTML = `
      <div class="shell">
        <div class="header">
          ${back ? `<button class="btn ghost" id="back">←</button>` : ""}
          <div>
            <div class="eyebrow">UNED Study</div>
            <h1>${escapeHtml(title)}</h1>
          </div>
        </div>
        ${body}
      </div>
    `;
    if (back) {
      document.getElementById("back").onclick = back;
    }
  }

  function loading(message = "Cargando…") {
    shell(`<div class="loading">${escapeHtml(message)}</div>`);
  }

  function showError(error, retry = home) {
    shell(
      `<div class="card error">
        <strong>No se ha podido completar la acción.</strong>
        <p class="muted small">${escapeHtml(error?.message || error)}</p>
        <button class="btn" id="retry">Volver</button>
      </div>`,
      "UNED Study"
    );
    document.getElementById("retry").onclick = retry;
  }

  function percent(value) {
    return value == null ? "—" : `${Math.round(value * 100)}%`;
  }

  async function home() {
    state.subjectId = null;
    state.sessionId = null;
    state.currentItem = null;
    loading();

    try {
      const data = await api("api/dashboard");
      state.dashboard = data;

      const cards = data.subjects.length
        ? data.subjects.map((subject) => {
            const p = subject.progress || {};
            const primary = subject.active_session
              ? "Continuar"
              : "Estudiar";
            const examInProgress =
              subject.active_session?.kind === "exam";
            return `
              <article class="card" data-subject="${escapeHtml(subject.id)}">
                <div class="subject-title">
                  <h2>${escapeHtml(subject.title)}</h2>
                  <button
                    class="btn star"
                    data-favorite="${escapeHtml(subject.id)}"
                    data-value="${subject.favorite ? "0" : "1"}"
                    aria-label="Favorito">
                    ${subject.favorite ? "★" : "☆"}
                  </button>
                </div>
                <div class="muted small">
                  ${subject.type === "test" ? "Test" : "Tarjetas"}
                </div>
                <div class="progress-line">
                  <span>${p.studied || 0}/${p.total || 0} estudiadas</span>
                  <span>${p.due || 0} para repasar</span>
                  <span>${percent(p.accuracy)} acierto</span>
                </div>
                <div class="actions">
                  <button class="btn hero-action" data-continue="${escapeHtml(subject.id)}">
                    ${primary}
                  </button>
                  ${examInProgress ? "" : `
                    <button class="btn secondary" data-topic="${escapeHtml(subject.id)}">
                      Tema
                    </button>
                    ${subject.exam_available ? `
                      <button class="btn secondary" data-exam="${escapeHtml(subject.id)}">
                        Simulacro
                      </button>
                    ` : ""}
                  `}
                </div>
              </article>
            `;
          }).join("")
        : `<div class="card">
            <strong>No hay asignaturas disponibles.</strong>
            <p class="muted small">El contenido se sincroniza automáticamente.</p>
          </div>`;

      const syncText = data.content?.last_error
        ? "Usando contenido guardado · sincronización pendiente"
        : data.content?.last_sync
          ? "Contenido actualizado automáticamente"
          : "Preparando contenido";

      shell(
        `
          <div class="grid">${cards}</div>
          <div class="footer">${escapeHtml(syncText)}</div>
        `,
        data.user?.name ? `Hola, ${data.user.name}` : "Asignaturas"
      );

      if (
        data.subjects.length === 0
        && !data.content?.last_error
        && !data.content?.last_sync
      ) {
        window.setTimeout(() => {
          if (!state.subjectId && !state.sessionId) home();
        }, 3000);
      }

      root.querySelectorAll("[data-favorite]").forEach((button) => {
        button.onclick = async () => {
          try {
            await api(
              `api/subjects/${encodeURIComponent(button.dataset.favorite)}/favorite`,
              {
                method: "POST",
                body: {favorite: button.dataset.value === "1"},
              }
            );
            await home();
          } catch (error) {
            showError(error);
          }
        };
      });

      root.querySelectorAll("[data-continue]").forEach((button) => {
        button.onclick = () => continueSubject(button.dataset.continue);
      });
      root.querySelectorAll("[data-topic]").forEach((button) => {
        button.onclick = () => topicPicker(button.dataset.topic);
      });
      root.querySelectorAll("[data-exam]").forEach((button) => {
        button.onclick = () => examIntro(button.dataset.exam);
      });
    } catch (error) {
      showError(error);
    }
  }

  async function continueSubject(subjectId) {
    loading("Preparando estudio…");
    try {
      const session = await api(
        `api/subjects/${encodeURIComponent(subjectId)}/continue`,
        {method: "POST"}
      );
      state.subjectId = subjectId;
      state.sessionId = session.session_id;
      if (session.kind === "exam") {
        await loadExam(session.session_id);
      } else {
        await nextStudyItem();
      }
    } catch (error) {
      showError(error);
    }
  }

  async function topicPicker(subjectId) {
    loading();
    try {
      const subject = await api(
        `api/subjects/${encodeURIComponent(subjectId)}`
      );
      state.subjectId = subjectId;
      const stats = new Map(
        (subject.statistics?.topics || []).map((item) => [item.id, item])
      );
      const topics = subject.topics.map((topic) => {
        const value = stats.get(topic.id) || {};
        return `
          <button class="topic" data-start-topic="${escapeHtml(topic.id)}">
            <strong>${escapeHtml(topic.title)}</strong>
            <span class="muted small">
              ${value.studied || 0}/${value.total || 0} estudiadas
              · ${value.due || 0} para repasar
            </span>
          </button>
        `;
      }).join("");

      shell(
        `<div class="topic-list">${topics}</div>`,
        subject.title,
        home
      );

      root.querySelectorAll("[data-start-topic]").forEach((button) => {
        button.onclick = async () => {
          loading("Preparando tema…");
          try {
            const session = await api(
              `api/subjects/${encodeURIComponent(subjectId)}/topic`,
              {
                method: "POST",
                body: {topic_id: button.dataset.startTopic},
              }
            );
            state.sessionId = session.session_id;
            await nextStudyItem();
          } catch (error) {
            showError(error, () => topicPicker(subjectId));
          }
        };
      });
    } catch (error) {
      showError(error);
    }
  }

  async function finishStudySession() {
    if (!state.sessionId) {
      await home();
      return;
    }
    try {
      await api(
        `api/sessions/${encodeURIComponent(state.sessionId)}/finish`,
        {method: "POST"}
      );
    } catch (_error) {
      // Returning home is still safe; the next load will expose any
      // remaining active session if the close request failed.
    }
    await home();
  }

  async function nextStudyItem() {
    loading("Buscando lo que más te conviene repasar…");
    try {
      const data = await api(
        `api/sessions/${encodeURIComponent(state.sessionId)}/next`
      );
      if (data.complete) {
        renderSessionComplete(data.session || {});
        return;
      }
      state.currentItem = data.item;
      state.itemStarted = performance.now();
      if (data.item.type === "test") {
        renderQuestion(data.item);
      } else {
        renderCard(data.item, false);
      }
    } catch (error) {
      showError(error);
    }
  }

  function renderQuestion(item) {
    shell(
      `
        <div class="card study-card">
          ${renderMarkdown(item.question_md)}
          <div class="answers">
            ${item.answers.map((answer) => `
              <button class="answer" data-answer="${escapeHtml(answer.id)}">
                ${renderMarkdown(answer.text_md)}
              </button>
            `).join("")}
          </div>
        </div>
      `,
      "Estudiar",
      home
    );

    root.querySelectorAll("[data-answer]").forEach((button) => {
      button.onclick = () => submitAnswer(button.dataset.answer);
    });
  }

  async function submitAnswer(answerId) {
    const elapsed = Math.round(performance.now() - state.itemStarted);
    root.querySelectorAll("[data-answer]").forEach((button) => {
      button.disabled = true;
    });

    try {
      const result = await api(
        `api/sessions/${encodeURIComponent(state.sessionId)}/answer`,
        {
          method: "POST",
          body: {
            item_id: state.currentItem.id,
            answer_id: answerId,
            request_id: crypto.randomUUID(),
            response_ms: elapsed,
          },
        }
      );

      const item = result.item;
      shell(
        `
          <div class="card study-card feedback ${result.correct ? "correct" : "incorrect"}">
            <h2>${result.correct ? "Correcta" : "Incorrecta"}</h2>
            ${item.explanation_md
              ? renderMarkdown(item.explanation_md)
              : ""}
            <div class="actions">
              <button class="btn" id="next">Siguiente</button>
              <button class="btn secondary" id="finish">Terminar</button>
            </div>
          </div>
        `,
        "Estudiar"
      );
      document.getElementById("next").onclick = nextStudyItem;
      document.getElementById("finish").onclick = finishStudySession;
    } catch (error) {
      showError(error);
    }
  }

  function renderCard(item, revealed) {
    shell(
      `
        <div class="card study-card">
          ${renderMarkdown(item.front_md)}
          ${revealed ? `
            <hr>
            ${renderMarkdown(item.back_md)}
            ${item.mnemonic_md ? renderMarkdown(item.mnemonic_md) : ""}
            <div class="rating">
              <button class="btn secondary" data-rating="again">Otra vez</button>
              <button class="btn secondary" data-rating="hard">Difícil</button>
              <button class="btn" data-rating="good">Bien</button>
              <button class="btn" data-rating="easy">Fácil</button>
            </div>
          ` : `
            ${item.hint_md
              ? `<div class="muted small">${renderMarkdown(item.hint_md)}</div>`
              : ""}
            <div class="actions">
              <button class="btn" id="reveal">Mostrar respuesta</button>
              <button class="btn secondary" id="finish">Terminar</button>
            </div>
          `}
        </div>
      `,
      "Estudiar",
      home
    );

    if (!revealed) {
      document.getElementById("reveal").onclick = () =>
        renderCard(item, true);
      document.getElementById("finish").onclick = finishStudySession;
    } else {
      root.querySelectorAll("[data-rating]").forEach((button) => {
        button.onclick = () => rateCard(button.dataset.rating);
      });
    }
  }

  async function rateCard(rating) {
    try {
      await api(
        `api/sessions/${encodeURIComponent(state.sessionId)}/rate`,
        {
          method: "POST",
          body: {
            item_id: state.currentItem.id,
            rating,
            request_id: crypto.randomUUID(),
            response_ms: Math.round(performance.now() - state.itemStarted),
          },
        }
      );
      await nextStudyItem();
    } catch (error) {
      showError(error);
    }
  }

  function renderSessionComplete(session) {
    const attempts =
      (session.correct_count || 0) + (session.incorrect_count || 0);
    const accuracy = attempts
      ? Math.round(100 * (session.correct_count || 0) / attempts)
      : null;

    shell(
      `
        <div class="card">
          <h2>Sesión completada</h2>
          <div class="stats">
            <div class="stat"><span class="muted small">Respondidas</span><strong>${session.answered_count || 0}</strong></div>
            <div class="stat"><span class="muted small">Acierto</span><strong>${accuracy == null ? "—" : accuracy + "%"}</strong></div>
          </div>
          <button class="btn" id="home">Volver a asignaturas</button>
        </div>
      `,
      "Buen trabajo"
    );
    document.getElementById("home").onclick = home;
  }

  async function examIntro(subjectId) {
    loading();
    try {
      const subject = await api(
        `api/subjects/${encodeURIComponent(subjectId)}`
      );
      state.subjectId = subjectId;
      const exam = subject.exam || {};
      const total = Math.min(
        Number(exam.questions || subject.statistics?.overall?.total || 0),
        Number(subject.statistics?.overall?.total || 0)
      );

      shell(
        `
          <div class="card">
            <h2>Simulacro</h2>
            <p class="muted">
              ${total} preguntas
              · ${Number(exam.duration_minutes || 60)} minutos
              · penalización por fallo: ${Number(exam.wrong_answer_penalty || 0)}
            </p>
            <p>
              La selección imita la importancia del contenido del examen y
              <strong>no utiliza tus fallos personales</strong>.
              La corrección se muestra únicamente al entregar.
            </p>
            <button class="btn" id="start-exam">Empezar simulacro</button>
          </div>
        `,
        subject.title,
        home
      );

      document.getElementById("start-exam").onclick = async () => {
        loading("Preparando simulacro…");
        try {
          const examState = await api(
            `api/subjects/${encodeURIComponent(subjectId)}/exam`,
            {method: "POST"}
          );
          state.sessionId = examState.session_id;
          renderExam(examState);
        } catch (error) {
          showError(error, () => examIntro(subjectId));
        }
      };
    } catch (error) {
      showError(error);
    }
  }

  async function loadExam(sessionId) {
    loading("Recuperando simulacro…");
    try {
      state.sessionId = sessionId;
      const examState = await api(
        `api/exams/${encodeURIComponent(sessionId)}`
      );
      state.subjectId = examState.subject_id;
      renderExam(examState);
    } catch (error) {
      showError(error);
    }
  }

  function formatTime(milliseconds) {
    const seconds = Math.max(0, Math.ceil(milliseconds / 1000));
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const rest = seconds % 60;
    return hours
      ? `${hours}:${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`
      : `${minutes}:${String(rest).padStart(2, "0")}`;
  }

  function startExamTimer(expiresAt) {
    clearExamTimer();
    const tick = () => {
      const clock = document.getElementById("clock");
      if (!clock) return;
      const remaining = new Date(expiresAt).getTime() - Date.now();
      clock.textContent = formatTime(remaining);
      if (remaining <= 0) {
        clearExamTimer();
        finishExam(false);
      }
    };
    tick();
    state.examTimer = setInterval(tick, 1000);
  }

  function renderExam(examState) {
    state.exam = examState;
    state.subjectId = examState.subject_id;
    const item = examState.item;

    shell(
      `
        <div class="exam-bar">
          <strong>Pregunta ${examState.index + 1} de ${examState.question_count}</strong>
          <span class="muted small">${examState.answered_count} respondidas</span>
          <span class="clock" id="clock">--:--</span>
        </div>
        <div class="card study-card">
          ${renderMarkdown(item.question_md)}
          <div class="answers">
            ${item.answers.map((answer) => `
              <button
                class="answer ${examState.selected_answer === answer.id ? "selected" : ""}"
                data-exam-answer="${escapeHtml(answer.id)}">
                ${renderMarkdown(answer.text_md)}
              </button>
            `).join("")}
          </div>
        </div>
        <div class="actions" style="margin-top:12px">
          <button class="btn secondary" id="prev" ${examState.index === 0 ? "disabled" : ""}>← Anterior</button>
          <button class="btn secondary" id="next" ${examState.index >= examState.question_count - 1 ? "disabled" : ""}>Siguiente →</button>
          <button class="btn" id="deliver">Entregar</button>
        </div>
      `,
      "Simulacro",
      home
    );

    root.querySelectorAll("[data-exam-answer]").forEach((button) => {
      button.onclick = () => saveExamAnswer(button.dataset.examAnswer);
    });
    document.getElementById("prev").onclick = () =>
      navigateExam(examState.index - 1);
    document.getElementById("next").onclick = () =>
      navigateExam(examState.index + 1);
    document.getElementById("deliver").onclick = () =>
      finishExam(true);
    startExamTimer(examState.expires_at);
  }

  async function saveExamAnswer(answerId) {
    try {
      const result = await api(
        `api/exams/${encodeURIComponent(state.sessionId)}/answer`,
        {
          method: "POST",
          body: {
            item_id: state.exam.item.id,
            answer_id: answerId,
          },
        }
      );
      state.exam.selected_answer = answerId;
      state.exam.answered_count = result.answered_count;
      renderExam(state.exam);
    } catch (error) {
      if (String(error?.message || error).toLowerCase().includes("expired")) {
        await finishExam(false);
        return;
      }
      showError(error);
    }
  }

  async function navigateExam(index) {
    try {
      const next = await api(
        `api/exams/${encodeURIComponent(state.sessionId)}/navigate`,
        {method: "POST", body: {index}}
      );
      renderExam(next);
    } catch (error) {
      showError(error);
    }
  }

  async function finishExam(confirmFirst) {
    if (
      confirmFirst
      && !window.confirm("¿Entregar el simulacro y ver la corrección?")
    ) {
      return;
    }
    clearExamTimer();
    loading("Corrigiendo simulacro…");
    try {
      const result = await api(
        `api/exams/${encodeURIComponent(state.sessionId)}/finish`,
        {method: "POST"}
      );
      renderExamResult(result);
    } catch (error) {
      showError(error);
    }
  }

  function renderExamResult(result) {
    const score = result.score || {};
    const review = (result.review || []).map((entry, index) => {
      const item = entry.item;
      const answerRows = item.answers.map((answer) => {
        let label = "";
        if (answer.id === item.correct_answer) label = "✓ correcta";
        else if (answer.id === entry.answer_id) label = "✗ tu respuesta";
        return `
          <div class="answer">
            ${renderMarkdown(answer.text_md)}
            ${label ? `<span class="muted small">${label}</span>` : ""}
          </div>
        `;
      }).join("");
      const status = entry.correct === true
        ? "Correcta"
        : entry.correct === false
          ? "Incorrecta"
          : "En blanco";
      return `
        <details class="card review">
          <summary>Pregunta ${index + 1} · ${status}</summary>
          ${renderMarkdown(item.question_md)}
          <div class="answers">${answerRows}</div>
          ${item.explanation_md ? `<hr>${renderMarkdown(item.explanation_md)}` : ""}
        </details>
      `;
    }).join("");

    shell(
      `
        <div class="card">
          <div class="stats">
            <div class="stat"><span class="muted small">Nota /10</span><strong>${Number(score.grade_10 || 0).toFixed(2)}</strong></div>
            <div class="stat"><span class="muted small">Correctas</span><strong>${score.correct || 0}</strong></div>
            <div class="stat"><span class="muted small">Incorrectas</span><strong>${score.incorrect || 0}</strong></div>
            <div class="stat"><span class="muted small">En blanco</span><strong>${score.blank || 0}</strong></div>
          </div>
          <p class="muted small">
            Penalización por fallo: ${Number(score.wrong_answer_penalty || 0)}
          </p>
          <button class="btn" id="home">Volver a asignaturas</button>
        </div>
        ${review}
      `,
      "Resultado del simulacro"
    );
    document.getElementById("home").onclick = home;
  }

  home();
})();
