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
  assignments: [], // 生成結果
  constraints: {
    // ハード制約
    hard_role_restrictions: { label: "役割別シフト制限（パート4専用等）", enabled: true },
    hard_day_off: { label: "希望休の厳守", enabled: true },
    hard_staff_count: { label: "人員配置基準（各時間帯の必要人数）", enabled: true },
    hard_night_rules: { label: "夜勤ルール（夜→夜/明、明→休）", enabled: true },
    hard_consecutive_limit: { label: "連続勤務制限（5連勤以下など）", enabled: true },
    hard_monthly_work_days: { label: "月間勤務日数固定（正社員等21日）", enabled: true },
    hard_kaigo_night_count: { label: "介護員夜勤回数固定（10回）", enabled: true },
    hard_part_time_limit: { label: "パート勤務日数上限（正社員以下）", enabled: true },
    // ソフト制約
    soft_part_time_principle: { label: "【中】パート原則勤務（希望休以外）", enabled: true },
    soft_part1_night: { label: "【中】パート1夜勤優先", enabled: true },
    soft_part2_late: { label: "【中】パート2遅番優先", enabled: true },
    soft_part3_balance: { label: "【中】パート3バランス（遅番/他）", enabled: true },
    soft_leader_support_balance: { label: "【中】責任者・サポート夜勤同程度", enabled: true },
    soft_leader_support_priority: { label: "【低】責任者・サポート早番優先＆同日回避", enabled: true }
  }
};

// 初期化
document.addEventListener('DOMContentLoaded', () => {
  console.log('ShifPita MVP loaded.');
  renderEmployeeTable();
  updateEmployeeSelect();
  renderCalendar();
  renderConstraints();

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
    let shiftSelectionHtml = '-';
    if (emp.role_id == 5) { // Part 4
      shiftSelectionHtml = '<div class="d-flex flex-wrap gap-1">';
      ['1', '2', '3', '4', '5', '6', '7', '8'].forEach(shift => {
        // available_shiftsが未定義の場合は全選択とみなす
        const isChecked = !emp.available_shifts || emp.available_shifts.includes(shift);
        shiftSelectionHtml += `
                <div class="form-check form-check-inline m-0">
                    <input class="form-check-input" type="checkbox" id="shift_${emp.id}_${shift}" 
                        ${isChecked ? 'checked' : ''} 
                        onchange="updateAvailableShifts(${emp.id}, '${shift}', this.checked)">
                    <label class="form-check-label small" for="shift_${emp.id}_${shift}">${shift}</label>
                </div>
            `;
      });
      shiftSelectionHtml += '</div>';
    }

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
            <td>${shiftSelectionHtml}</td>
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
  if (emp) {
    emp.role_id = parseInt(roleId);
    // パート4に変更された場合、未設定ならランダム生成
    if (emp.role_id === 5 && !emp.available_shifts) {
      randomizeAvailableShifts(emp);
    }
    renderEmployeeTable(); // 役割変更に伴いシフト選択欄を更新
  }
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

function updateAvailableShifts(id, shift, isChecked) {
  const emp = state.employees.find(e => e.id === id);
  if (!emp) return;

  // available_shiftsが未定義の場合は全シフトが有効な状態からスタート
  if (!emp.available_shifts) {
    emp.available_shifts = ['1', '2', '3', '4', '5', '6', '7', '8'];
  }

  if (isChecked) {
    if (!emp.available_shifts.includes(shift)) {
      emp.available_shifts.push(shift);
    }
  } else {
    emp.available_shifts = emp.available_shifts.filter(s => s !== shift);
  }
  // console.log(`Employee ${id} available shifts:`, emp.available_shifts);
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

// 制約条件描画
function renderConstraints() {
  const container = document.getElementById('constraintsArea');
  container.innerHTML = '';

  const hardConstraints = [];
  const softConstraints = [];

  Object.entries(state.constraints).forEach(([key, config]) => {
    if (key.startsWith('hard_')) {
      hardConstraints.push([key, config]);
    } else {
      softConstraints.push([key, config]);
    }
  });

  const renderGroup = (title, items, headerClass) => {
    const headerCol = document.createElement('div');
    headerCol.className = 'col-12 mt-2';
    headerCol.innerHTML = `<h6 class="${headerClass} fw-bold border-bottom pb-2">${title}</h6>`;
    container.appendChild(headerCol);

    items.forEach(([key, config]) => {
      const col = document.createElement('div');
      col.className = 'col-md-6';
      col.innerHTML = `
        <div class="form-check">
          <input class="form-check-input" type="checkbox" id="const_${key}" 
            ${config.enabled ? 'checked' : ''} 
            onchange="state.constraints['${key}'].enabled = this.checked">
          <label class="form-check-label" for="const_${key}">${config.label}</label>
        </div>
      `;
      container.appendChild(col);
    });
  };

  renderGroup('ハード制約（必須遵守）', hardConstraints, 'text-danger');
  renderGroup('ソフト制約（推奨・重み付き）', softConstraints, 'text-primary');
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
        special_days: [], // 今回は未実装
        enabled_constraints: Object.keys(state.constraints).filter(k => state.constraints[k].enabled)
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

function randomizeAvailableShifts(emp) {
  emp.available_shifts = [];
  ['1', '2', '3', '4', '5', '6', '7', '8'].forEach(shift => {
    if (Math.random() < 0.5) emp.available_shifts.push(shift);
  });
  if (emp.available_shifts.length === 0) {
    const randomShift = String(Math.floor(Math.random() * 8) + 1);
    emp.available_shifts.push(randomShift);
  }
}