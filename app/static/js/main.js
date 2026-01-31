// Main JavaScript

// 状態管理
let state = {
  year: 2026,
  month: 10,
  employees: [
    { id: 1, name: "佐藤", role_id: 1, day_off_requests: [] },
    { id: 2, name: "鈴木", role_id: 2, day_off_requests: [] },
    { id: 3, name: "高橋", role_id: 3, day_off_requests: [] }
  ],
  assignments: [] // 生成結果
};

// 初期化
document.addEventListener('DOMContentLoaded', () => {
  console.log('ShifPita MVP loaded.');
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

  // ヘッダー
  const thead = document.createElement('thead');
  const headerRow = document.createElement('tr');
  headerRow.innerHTML = '<th>氏名</th>';

  // 日付列（assignmentsから抽出またはカレンダーから）
  const daysInMonth = new Date(state.year, state.month, 0).getDate();
  for (let d = 1; d <= daysInMonth; d++) {
    headerRow.innerHTML += `<th>${d}</th>`;
  }
  thead.appendChild(headerRow);
  table.appendChild(thead);

  // ボディ
  const tbody = document.createElement('tbody');
  state.employees.forEach(emp => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${emp.name}</td>`;
    for (let d = 1; d <= daysInMonth; d++) {
      const dateStr = `${state.year}-${String(state.month).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
      const assignment = state.assignments.find(a => a.employee_id === emp.id && a.date === dateStr);
      const shift = assignment ? assignment.shift_type : '-';
      tr.innerHTML += `<td>${shift}</td>`;
    }
    tbody.appendChild(tr);
  });
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