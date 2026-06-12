const state = {
  rows: [],
  query: "",
  semester: "",
};

const list = document.getElementById("archive-list");
const empty = document.getElementById("empty-state");
const search = document.getElementById("search");
const semester = document.getElementById("semester");
const itemCount = document.getElementById("item-count");
const semesterCount = document.getElementById("semester-count");

function clean(value) {
  return String(value || "").trim();
}

// 비공개/재캡처 대상은 외부 공개 색인에서 숨긴다.
const HIDDEN_STATUSES = new Set(["recapture-needed", "private"]);

function status(row) {
  return clean(row.status).toLowerCase() || "pending";
}

// 공개 사이트에는 재생 가능한 보존본만 노출한다.
function isPublic(row) {
  return Boolean(clean(row.wacz_url)) && !HIDDEN_STATUSES.has(status(row));
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

  return isPublic(row) &&
    (!state.semester || row.semester === state.semester) &&
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
  const rows = state.rows.filter(isPublic);
  const semesters = new Set(rows.map((row) => clean(row.semester)).filter(Boolean));
  itemCount.textContent = `${rows.length} works`;
  semesterCount.textContent = `${semesters.size} semesters`;
}

function renderSemesterOptions() {
  const semesters = Array.from(
    new Set(state.rows.filter(isPublic).map((row) => clean(row.semester)).filter(Boolean))
  ).sort().reverse();
  for (const value of semesters) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    semester.appendChild(option);
  }
}

function renderRows() {
  list.innerHTML = "";
  const rows = state.rows.filter(matches);
  empty.hidden = rows.length > 0;

  rows.forEach((row, index) => {
    const item = document.createElement("a");
    item.className = "archive-row";
    item.href = viewerUrl(row);
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

    item.append(number, work, student, term);
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
