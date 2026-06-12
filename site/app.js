const state = {
  rows: [],
  query: "",
  semester: "",
  status: "",
};

const list = document.getElementById("archive-list");
const empty = document.getElementById("empty-state");
const search = document.getElementById("search");
const semester = document.getElementById("semester");
const statusFilter = document.getElementById("status");
const itemCount = document.getElementById("item-count");
const semesterCount = document.getElementById("semester-count");

function clean(value) {
  return String(value || "").trim();
}

// 상태값 규칙(운영 가이드 4.6): ok 공개, partial 공개+주석, review-needed 조건부
// 공개(재생 비활성), recapture-needed/private 숨김.
const HIDDEN_STATUSES = new Set(["recapture-needed", "private"]);
const PLAYABLE_STATUSES = new Set(["ok", "partial"]);

function status(row) {
  return clean(row.status).toLowerCase() || "pending";
}

function isVisible(row) {
  return !HIDDEN_STATUSES.has(status(row));
}

function matches(row) {
  const q = state.query.toLowerCase();
  const haystack = [
    row.title,
    row.student_name,
    row.semester,
    row.original_url,
    row.notes,
  ].map(clean).join(" ").toLowerCase();

  return isVisible(row) &&
    (!state.semester || row.semester === state.semester) &&
    (!state.status || status(row) === state.status) &&
    (!q || haystack.includes(q));
}

function viewerUrl(row) {
  const params = new URLSearchParams({
    title: clean(row.title) || clean(row.original_url),
    student: clean(row.student_name),
    url: clean(row.original_url),
    source: clean(row.wacz_url),
  });
  return `viewer.html?${params.toString()}`;
}

function renderSummary() {
  const rows = state.rows.filter(isVisible);
  const semesters = new Set(rows.map((row) => clean(row.semester)).filter(Boolean));
  itemCount.textContent = `${rows.length} works`;
  semesterCount.textContent = `${semesters.size} semesters`;
}

function renderSemesterOptions() {
  const semesters = Array.from(
    new Set(state.rows.filter(isVisible).map((row) => clean(row.semester)).filter(Boolean))
  ).sort().reverse();
  for (const value of semesters) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    semester.appendChild(option);
  }
}

function renderStatusOptions() {
  const statuses = Array.from(
    new Set(state.rows.map(status).filter((value) => !HIDDEN_STATUSES.has(value)))
  ).sort();

  for (const value of statuses) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    statusFilter.appendChild(option);
  }
}

function renderRows() {
  list.innerHTML = "";
  const rows = state.rows.filter(matches);
  empty.hidden = rows.length > 0;

  rows.forEach((row, index) => {
    const playable = Boolean(clean(row.wacz_url)) && PLAYABLE_STATUSES.has(status(row));
    const item = document.createElement(playable ? "a" : "div");
    item.className = playable ? "archive-row" : "archive-row is-disabled";
    if (playable) item.href = viewerUrl(row);
    if (clean(row.notes)) item.title = clean(row.notes);

    const number = document.createElement("span");
    number.className = "row-number";
    number.textContent = String(index + 1).padStart(2, "0");

    const work = document.createElement("span");
    work.className = "work";
    work.textContent = clean(row.title) || clean(row.original_url) || "Untitled";

    const student = document.createElement("span");
    student.textContent = clean(row.student_name) || "-";

    const term = document.createElement("span");
    term.textContent = clean(row.semester) || "-";

    const statusCell = document.createElement("span");
    statusCell.className = `status status-${status(row)}`;
    statusCell.textContent = status(row);

    item.append(number, work, student, term, statusCell);
    list.appendChild(item);
  });
}

fetch("index.json", { cache: "no-store" })
  .then((response) => {
    if (!response.ok) throw new Error("index");
    return response.json();
  })
  .then((rows) => {
    state.rows = Array.isArray(rows) ? rows : [];
    renderSummary();
    renderSemesterOptions();
    renderStatusOptions();
    renderRows();
  })
  .catch(() => {
    empty.hidden = false;
    empty.textContent = "Archive index is unavailable.";
  });

search.addEventListener("input", (event) => {
  state.query = event.target.value;
  renderRows();
});

semester.addEventListener("change", (event) => {
  state.semester = event.target.value;
  renderRows();
});

statusFilter.addEventListener("change", (event) => {
  state.status = event.target.value;
  renderRows();
});
