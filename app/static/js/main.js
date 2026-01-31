// Main JavaScript

// 状態管理
let state = {
  year: 2026,
  month: 10,
  employees: [
    { id: 1, name: "責任者A", role_id: 6, day_off_requests: [] },
    { id: 2, name: "サポートB", role_id: 7, day_off_requests: [] },
    { id: 3, name: "介護員C", role_id: 1, day_off_requests: [] },
    { id: 4, name: "介護員D", role_id: 1, day_off_requests: [] },
    { id: 5, name: "介護員E", role_id: 1, day_off_requests: [] },
    { id: 6, name: "介護員F", role_id: 1, day_off_requests: [] },
    { id: 7, name: "介護員G", role_id: 1, day_off_requests: [] },
    { id: 8, name: "パート1H", role_id: 2, day_off_requests: [] },
    { id: 9, name: "パート2I", role_id: 3, day_off_requests: [] },
    { id: 10, name: "パート3J", role_id: 4, day_off_requests: [] },
    { id: 11, name: "パート4K", role_id: 5, day_off_requests: [] },
    { id: 12, name: "パート4L", role_id: 5, day_off_requests: [] },
    { id: 13, name: "パート4M", role_id: 5, day_off_requests: [] },
    { id: 14, name: "パート4N", role_id: 5, day_off_requests: [] },
    { id: 15, name: "パート4O", role_id: 5, day_off_requests: [] },
    { id: 16, name: "パート4P", role_id: 5, day_off_requests: [] },
    { id: 17, name: "パート4Q", role_id: 5, day_off_requests: [] },
    { id: 18, name: "パート4R", role_id: 5, day_off_requests: [] },
    { id: 19, name: "パート4S", role_id: 5, day_off_requests: [] }
  ],
  assignments: [] // 生成結果
};

// 初期化
document.addEventListener('DOMContentLoaded', () => {
  console.log('ShifPita MVP loaded.');
  generateRandomDayOffs(); // テスト用：初期希望休設定
  renderEmployeeTable();
  updateEmployeeSelect();
  renderCalendar();

  // 年月変更イベント
  document.getElementById('yearInput').addEventListener('change', (e) => {
    state.year = parseInt(e.target.value);
    renderCalendar();
  });
  document.getElementById('monthInput').addEventListener('change', (e) => {
    state.month = parseInt(e.target.value);
    renderCalendar();
  });
});

// 従業員テーブル描画
function renderEmployeeTable() {
  const tbody = document.getElementById('employeeTableBody');
  tbody.innerHTML = '';

  state.employees.forEach((emp, index) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
            <td><input type="text" class="form-control form-control-sm" value="${emp.name}" onchange="updateEmployeeName(${emp.id}, this.value)"></td>
            <td>
                <select class="form-select form-select-sm" onchange="updateEmployeeRole(${emp.id}, this.value)">
                    <option value="1" ${emp.role_id == 1 ? 'selected' : ''}>介護員</option>
                    <option value="2" ${emp.role_id == 2 ? 'selected' : ''}>パート1</option>
                    <option value="3" ${emp.role_id == 3 ? 'selected' : ''}>パート2</option>
                    <option value="4" ${emp.role_id == 4 ? 'selected' : ''}>パート3</option>
                    <option value="5" ${emp.role_id == 5 ? 'selected' : ''}>パート4</option>
                    <option value="6" ${emp.role_id == 6 ? 'selected' : ''}>責任者</option>
                    <option value="7" ${emp.role_id == 7 ? 'selected' : ''}>サポート</option>
                </select>
            </td>
            <td><button class="btn btn-sm btn-danger" onclick="removeEmployee(${emp.id})">削除</button></td>
        `;
    tbody.appendChild(tr);
  });
}

// 従業員操作
function addEmployee() {
  const newId = state.employees.length > 0 ? Math.max(...state.employees.map(e => e.id)) + 1 : 1;
  state.employees.push({ id: newId, name: "新規スタッフ", role_id: 1, day_off_requests: [] });
  renderEmployeeTable();
  updateEmployeeSelect();
}

function removeEmployee(id) {
  state.employees = state.employees.filter(e => e.id !== id);
  renderEmployeeTable();
  updateEmployeeSelect();
  renderCalendar(); // 選択中の従業員が消えた場合の対応が必要だが簡易的に再描画
}

function updateEmployeeName(id, name) {
  const emp = state.employees.find(e => e.id === id);
  if (emp) emp.name = name;
  updateEmployeeSelect(); // セレクトボックスの名前も更新
}

function updateEmployeeRole(id, roleId) {
  const emp = state.employees.find(e => e.id === id);
  if (emp) emp.role_id = parseInt(roleId);
}

function updateEmployeeSelect() {
  const select = document.getElementById('currentEmployeeSelect');
  const currentVal = select.value;
  select.innerHTML = '';
  state.employees.forEach(emp => {
    const option = document.createElement('option');
    option.value = emp.id;
    option.textContent = emp.name;
    select.appendChild(option);
  });
  if (currentVal && state.employees.find(e => e.id == currentVal)) {
    select.value = currentVal;
  }
}

// カレンダー描画
function renderCalendar() {
  const container = document.getElementById('calendarArea');
  container.innerHTML = '';

  const empId = parseInt(document.getElementById('currentEmployeeSelect').value);
  const emp = state.employees.find(e => e.id === empId);
  if (!emp) return;

  const daysInMonth = new Date(state.year, state.month, 0).getDate();
  const firstDay = new Date(state.year, state.month - 1, 1).getDay(); // 0:Sun, 1:Mon...
  const weekdays = ['日', '月', '火', '水', '木', '金', '土'];

  // 曜日ヘッダー
  weekdays.forEach((day, index) => {
    const header = document.createElement('div');
    header.className = `calendar-header ${index === 0 ? 'text-danger' : index === 6 ? 'text-primary' : ''}`;
    header.textContent = day;
    container.appendChild(header);
  });

  // 月初の空白セル
  for (let i = 0; i < firstDay; i++) {
    container.appendChild(document.createElement('div'));
  }

  for (let d = 1; d <= daysInMonth; d++) {
    const dateStr = `${state.year}-${String(state.month).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
    const isOff = emp.day_off_requests.includes(dateStr);

    const cell = document.createElement('div');
    cell.className = `calendar-cell ${isOff ? 'off' : ''}`;
    cell.textContent = d;
    cell.onclick = () => toggleDayOff(empId, dateStr);
    container.appendChild(cell);
  }
}

function toggleDayOff(empId, dateStr) {
  const emp = state.employees.find(e => e.id === empId);
  if (!emp) return;

  if (emp.day_off_requests.includes(dateStr)) {
    emp.day_off_requests = emp.day_off_requests.filter(d => d !== dateStr);
  } else {
    emp.day_off_requests.push(dateStr);
  }
  renderCalendar();
}

// シフト生成 API呼び出し
async function generateShifts() {
  const modal = new bootstrap.Modal(document.getElementById('loadingModal'));
  modal.show();

  try {
    const response = await fetch('/api/shifts/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        year: state.year,
        month: state.month,
        employees: state.employees,
        special_days: [] // 今回は未実装
      })
    });

    const result = await response.json();

    // モーダルを閉じる（少し待つ）
    setTimeout(() => modal.hide(), 500);

    if (response.ok) {
      state.assignments = result.assignments;
      document.getElementById('resultArea').classList.remove('d-none');
      renderPreview();
      // 結果エリアへスクロール
      document.getElementById('resultArea').scrollIntoView({ behavior: 'smooth' });
    } else {
      alert('エラー: ' + result.message);
    }
  } catch (error) {
    modal.hide();
    alert('通信エラーが発生しました。');
    console.error(error);
  }
}

// プレビュー描画
function renderPreview() {
  const table = document.getElementById('previewTable');
  table.innerHTML = '';

  const daysInMonth = new Date(state.year, state.month, 0).getDate();

  // 集計用配列
  const counts7_16 = new Array(daysInMonth).fill(0);
  const counts16_20 = new Array(daysInMonth).fill(0);
  const counts20_07 = new Array(daysInMonth).fill(0);

  // シフト定義 (JS側でも定義が必要)
  const shifts7_16 = ["早1", "早2", "日1", "日2", "1", "2", "3", "4", "5", "6", "7", "8"];
  const shifts16_20 = ["日1", "日2", "遅1", "遅2", "8"];
  const shifts20_07 = ["夜1", "夜2"];

  // ヘッダー
  const weekdays = ['日', '月', '火', '水', '木', '金', '土'];
  const thead = document.createElement('thead');
  const headerRow = document.createElement('tr');
  headerRow.innerHTML = '<th>氏名</th>';
  for (let d = 1; d <= daysInMonth; d++) {
    const date = new Date(state.year, state.month - 1, d);
    const dayIndex = date.getDay();
    const dayName = weekdays[dayIndex];
    const colorClass = dayIndex === 0 ? 'text-danger' : dayIndex === 6 ? 'text-primary' : '';

    headerRow.innerHTML += `<th class="${colorClass}">${d}<br><small>${dayName}</small></th>`;
  }
  headerRow.innerHTML += '<th>出勤日数</th><th>夜勤回数</th>';
  thead.appendChild(headerRow);
  table.appendChild(thead);

  // ボディ
  const tbody = document.createElement('tbody');
  state.employees.forEach(emp => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${emp.name}</td>`;

    let workDays = 0;
    let nightCount = 0;

    for (let d = 1; d <= daysInMonth; d++) {
      const dateStr = `${state.year}-${String(state.month).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
      const assignment = state.assignments.find(a => a.employee_id === emp.id && a.date === dateStr);
      const shift = assignment ? assignment.shift_type : '';

      tr.innerHTML += `<td>${shift || '-'}</td>`;

      // 集計
      if (shift && shift !== '休' && shift !== '明') {
        workDays++;
      }
      if (shifts20_07.includes(shift)) {
        nightCount++;
      }

      if (shifts7_16.includes(shift)) counts7_16[d - 1]++;
      if (shifts16_20.includes(shift)) counts16_20[d - 1]++;
      if (shifts20_07.includes(shift)) counts20_07[d - 1]++;
    }

    tr.innerHTML += `<td>${workDays}</td><td>${nightCount}</td>`;
    tbody.appendChild(tr);
  });

  // 集計行 (Footer)
  const addCountRow = (label, counts) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${label}</td>`;
    counts.forEach(c => {
      tr.innerHTML += `<td>${c}</td>`;
    });
    tr.innerHTML += '<td>-</td><td>-</td>';
    tbody.appendChild(tr);
  };

  addCountRow('7-16時', counts7_16);
  addCountRow('16-20時', counts16_20);
  addCountRow('20-翌7時', counts20_07);

  table.appendChild(tbody);
}

// PDFダウンロード
async function downloadPDF() {
  const response = await fetch('/api/shifts/download', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(state) // 現在の状態（assignments含む）を送信
  });

  if (response.ok) {
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `shift_${state.year}_${state.month}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  } else {
    alert('PDF生成に失敗しました。');
  }
}

// テスト用：ランダム希望休生成
function generateRandomDayOffs() {
  const partTimeRoles = [2, 3, 4, 5]; // パートのロールID
  const daysInMonth = new Date(state.year, state.month, 0).getDate();

  state.employees.forEach(emp => {
    const isPartTime = partTimeRoles.includes(emp.role_id);
    const count = isPartTime ? 17 : 2;
    const requests = new Set();
    while (requests.size < count) {
      const d = Math.floor(Math.random() * daysInMonth) + 1;
      const dateStr = `${state.year}-${String(state.month).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
      requests.add(dateStr);
    }
    emp.day_off_requests = Array.from(requests).sort();
  });
}