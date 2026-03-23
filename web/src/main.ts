import './style.css';
import {
  buildStateMessage,
  deriveSnapshotView,
  loadSnapshot,
  type ServerRow,
  type SnapshotView,
} from './data';
import { AFF_ID } from './constants';

const DATA_URL = './data/latest.json';

// ── DOM refs ────────────────────────────────────────────────────────
const searchInput = getElement<HTMLInputElement>('#search-input');
const categoryFilter = getElement<HTMLSelectElement>('#category-filter');
const locationFilter = getElement<HTMLSelectElement>('#location-filter');
const dc02Filter = getElement<HTMLInputElement>('#dc02-filter');
const dc03Filter = getElement<HTMLInputElement>('#dc03-filter');

const resetButton = getElement<HTMLButtonElement>('#reset-button');
const dataStatus = getElement<HTMLElement>('#data-status');
const resultSummary = getElement<HTMLElement>('#result-summary');
const statUpdated = getElement<HTMLElement>('#stat-updated');

const tableState = getElement<HTMLElement>('#table-state');
const tableStateTitle = getElement<HTMLElement>('#table-state-title');
const tableStateDescription = getElement<HTMLElement>('#table-state-description');
const tableHost = getElement<HTMLElement>('#table-host');

let currentView: SnapshotView | null = null;
const themeToggle = getElement<HTMLButtonElement>('#theme-toggle');

let sortColumn: string = 'billing_cycle_annually_usd';
let sortDirection: 'asc' | 'desc' = 'asc';

// ── Theme ───────────────────────────────────────────────────────────
type Theme = 'light' | 'dark';

function detectSystemTheme(): Theme {
  try {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  } catch {
    return 'light';
  }
}

function getStoredTheme(): Theme | null {
  const stored = localStorage.getItem('theme');
  return stored === 'light' || stored === 'dark' ? stored : null;
}

function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem('theme', theme);
}

applyTheme(getStoredTheme() ?? 'light');

// ── Bootstrap ───────────────────────────────────────────────────────
bindEvents();
void loadAndRender();

function bindEvents(): void {
  const apply = () => applyFilters();

  searchInput.addEventListener('input', apply);
  categoryFilter.addEventListener('change', apply);
  locationFilter.addEventListener('change', apply);
  dc02Filter.addEventListener('change', apply);
  dc03Filter.addEventListener('change', apply);

  resetButton.addEventListener('click', () => {
    searchInput.value = '';
    categoryFilter.value = '';
    locationFilter.value = '';
    dc02Filter.checked = false;
    dc03Filter.checked = false;
    applyFilters();
  });
  themeToggle.addEventListener('click', () => {
    const current = document.documentElement.dataset.theme;
    applyTheme(current === 'dark' ? 'light' : 'dark');
  });

  // Forward wheel events from anywhere on the page to the table scroll container
  document.addEventListener('wheel', (e) => {
    if (tableHost.contains(e.target as Node)) return;
    tableHost.scrollTop += e.deltaY;
  }, { passive: true });
}

async function loadAndRender(): Promise<void> {
  setUiBusy(true);
  renderTableState('loading');

  try {
    const snapshot = await loadSnapshot(DATA_URL);
    const view = deriveSnapshotView(snapshot);
    currentView = view;

    renderOverview(view);
    syncSelectOptions(categoryFilter, view.categoryOptions, '全部分类');
    syncSelectOptions(locationFilter, view.locationOptions, '全部机房');

    if (view.rows.length === 0) {
      updateStatus('数据为空');
      tableHost.hidden = true;
      renderTableState('empty');
      resultSummary.textContent = '当前无套餐可展示';
      return;
    }

    updateStatus(`${view.summary.itemCount} 条`);

    tableHost.hidden = false;
    renderTableState('ready');
    applyFilters();
  } catch (error) {
    const detail = error instanceof Error ? error.message : '未知错误';
    updateStatus('加载失败', true);
    tableHost.hidden = true;
    renderTableState('error', detail);
    resultSummary.textContent = '无法渲染表格';
  } finally {
    setUiBusy(false);
  }
}

// ── Filtering ───────────────────────────────────────────────────────
function applyFilters(): void {
  if (currentView === null) return;

  const filterState = {
    search: searchInput.value.trim().toLowerCase(),
    category: categoryFilter.value,
    location: locationFilter.value,
    dc02Only: dc02Filter.checked,
    dc03Only: dc03Filter.checked,
  };

  const filtered = currentView.rows.filter((row) => matchesFilters(row, filterState));
  const sorted = sortRows(filtered);

  resultSummary.textContent = `${filtered.length} / ${currentView.rows.length}`;
  renderTable(sorted);
}

function matchesFilters(
  row: ServerRow,
  f: { search: string; category: string; location: string; dc02Only: boolean; dc03Only: boolean },
): boolean {
  if (f.search !== '' && !row.search_blob.includes(f.search)) return false;
  if (f.category !== '' && row.category_name !== f.category) return false;
  if (f.location !== '' && !row.normalized_locations.includes(f.location)) return false;
  if (f.dc02Only && !row.supportsDc02) return false;
  if (f.dc03Only && !row.supportsDc03) return false;
  return true;
}

// ── Sorting ─────────────────────────────────────────────────────────
function sortRows(rows: ServerRow[]): ServerRow[] {
  const col = sortColumn;
  const dir = sortDirection === 'asc' ? 1 : -1;

  return [...rows].sort((a, b) => {
    const va = getSortValue(a, col);
    const vb = getSortValue(b, col);

    if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * dir;
    return String(va).localeCompare(String(vb), 'zh-CN') * dir;
  });
}

function getSortValue(row: ServerRow, col: string): string | number {
  switch (col) {
    case 'store_title': return row.store_title;
    case 'billing_cycle_annually_usd': return row.billing_cycle_annually_usd;
    case 'supportsDc02': return row.supportsDc02 ? 0 : 1;
    case 'supportsDc03': return row.supportsDc03 ? 0 : 1;
    case 'category_name': return row.category_name;
    default: return row.store_title;
  }
}

function handleSort(col: string): void {
  if (sortColumn === col) {
    sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
  } else {
    sortColumn = col;
    sortDirection = 'asc';
  }
  applyFilters();
}

// ── Render table ────────────────────────────────────────────────────
type ColumnDef = {
  key: string;
  label: string;
  sortable: boolean;
  thClass?: string;
};

const COLUMNS: ColumnDef[] = [
  { key: 'store_title', label: '型号', sortable: true },
  { key: 'billing_cycle_annually_usd', label: '年付', sortable: true },
  { key: 'dc', label: 'DC', sortable: false },
  { key: 'specs', label: '配置信息', sortable: false },
  { key: 'locations', label: '机房', sortable: false },
  { key: 'actions', label: '购买链接', sortable: false },
];

function renderTable(rows: ServerRow[]): void {
  const table = document.createElement('table');
  table.className = 'data-grid';

  // thead
  const thead = document.createElement('thead');
  const headerRow = document.createElement('tr');

  for (const col of COLUMNS) {
    const th = document.createElement('th');
    th.textContent = col.label;

    if (col.sortable) {
      th.addEventListener('click', () => handleSort(col.key));
      if (sortColumn === col.key) {
        th.classList.add(sortDirection === 'asc' ? 'sort-asc' : 'sort-desc');
      }
    }

    if (col.thClass) th.classList.add(col.thClass);
    headerRow.appendChild(th);
  }

  thead.appendChild(headerRow);
  table.appendChild(thead);

  // tbody
  const tbody = document.createElement('tbody');

  if (rows.length === 0) {
    const tr = document.createElement('tr');
    tr.className = 'empty-row';
    const td = document.createElement('td');
    td.colSpan = COLUMNS.length;
    td.textContent = '没有匹配的套餐';
    tr.appendChild(td);
    tbody.appendChild(tr);
  } else {
    for (const row of rows) {
      tbody.appendChild(buildRow(row));
    }
  }

  table.appendChild(tbody);

  tableHost.replaceChildren(table);
}

function buildRow(row: ServerRow): HTMLTableRowElement {
  const tr = document.createElement('tr');

  const buyUrl =
    (row.pid ?? 0) > 0
      ? `https://my.racknerd.com/aff.php?aff=${AFF_ID}&a=add&pid=${row.pid}`
      : `${row.confproduct_url}&aff=${AFF_ID}`;

  // 1. Model (with hyperlink + category)
  const tdModel = td();
  const link = document.createElement('a');
  link.className = 'model-link';
  link.href = buyUrl;
  link.target = '_blank';
  link.rel = 'noreferrer';
  link.innerHTML =
    `<span class="model-name">${esc(row.store_title)}</span>` +
    `<span class="model-category">${esc(row.category_name)}</span>`;
  tdModel.appendChild(link);
  tr.appendChild(tdModel);

  // 2. Price
  const tdPrice = td();
  tdPrice.innerHTML =
    `<span class="price-tag">$${row.billing_cycle_annually_usd.toFixed(2)}<span class="price-unit">/yr</span></span>`;
  tr.appendChild(tdPrice);

  // 3. DC-02 / DC-03
  const tdDc = td();
  tdDc.innerHTML =
    `<div class="dc-cell">` +
    dcBadge('02', row.supportsDc02) +
    dcBadge('03', row.supportsDc03) +
    `</div>`;
  tr.appendChild(tdDc);

  // 4. Specs card
  const tdSpecs = td();
  tdSpecs.innerHTML = buildSpecsCard(row);
  tr.appendChild(tdSpecs);

  // 5. Locations
  const tdLoc = td();
  tdLoc.innerHTML = buildLocations(row);
  tr.appendChild(tdLoc);

  // 6. Actions
  const tdActions = td();
  tdActions.innerHTML =
    `<a class="action-link primary" href="${esc(buyUrl)}" target="_blank" rel="noreferrer">下单</a>`;
  tr.appendChild(tdActions);

  return tr;
}

function buildSpecsCard(row: ServerRow): string {
  const items: string[] = [];
  const cpu = row.specs.cpu;
  const mem = row.display_memory;
  const disk = row.display_disk;
  const bw = row.display_bandwidth;

  if (cpu && cpu !== '--') items.push(specItem('⚙', cpu));
  if (mem !== '--') items.push(specItem('◈', mem));
  if (disk !== '--') items.push(specItem('▪', disk));
  if (bw !== '--') items.push(specItem('↕', bw));

  return `<div class="specs-card">${items.join('')}</div>`;
}

function specItem(icon: string, value: string): string {
  return `<div class="spec-item"><span class="spec-icon">${icon}</span><span class="spec-value">${esc(value)}</span></div>`;
}

function buildLocations(row: ServerRow): string {
  const chips = row.normalized_locations.map((loc) => {
    const isDc = loc.includes('DC-02') || loc.includes('DC-03');
    const cls = isDc ? 'loc-chip dc-highlight' : 'loc-chip';
    return `<span class="${cls}">${esc(loc)}</span>`;
  });
  return `<div class="locations-cell">${chips.join('')}</div>`;
}

function dcBadge(code: string, active: boolean): string {
  const cls = active ? 'dc-badge active' : 'dc-badge inactive';
  const label = active ? `DC-${code} ✓` : `DC-${code}`;
  return `<span class="${cls}">${label}</span>`;
}

// ── Overview / stats ────────────────────────────────────────────────
function renderOverview(view: SnapshotView): void {
  statUpdated.textContent = view.summary.updatedAtLabel;
}

// ── Helpers ─────────────────────────────────────────────────────────
function syncSelectOptions(
  select: HTMLSelectElement,
  options: string[],
  allLabel: string,
): void {
  const prev = select.value;
  select.replaceChildren();

  const allOpt = document.createElement('option');
  allOpt.value = '';
  allOpt.textContent = allLabel;
  select.append(allOpt);

  for (const v of options) {
    const opt = document.createElement('option');
    opt.value = v;
    opt.textContent = v;
    select.append(opt);
  }

  if (options.includes(prev)) select.value = prev;
}

function renderTableState(kind: 'loading' | 'error' | 'empty' | 'ready', detail?: string): void {
  if (kind === 'ready') {
    tableState.hidden = true;
    return;
  }

  const message = buildStateMessage(kind, detail);
  tableState.hidden = false;
  tableStateTitle.textContent = message.title;
  tableStateDescription.innerHTML = message.description;
}

function updateStatus(label: string, isError = false): void {
  dataStatus.textContent = label;
  dataStatus.dataset.tone = isError ? 'error' : 'default';
}

function setUiBusy(isBusy: boolean): void {

  resetButton.disabled = isBusy;
  searchInput.disabled = isBusy;
  categoryFilter.disabled = isBusy;
  locationFilter.disabled = isBusy;
  dc02Filter.disabled = isBusy;
  dc03Filter.disabled = isBusy;
}

function getElement<T extends Element>(selector: string): T {
  const el = document.querySelector<T>(selector);
  if (el === null) throw new Error(`Missing required element: ${selector}`);
  return el;
}

function td(): HTMLTableCellElement {
  return document.createElement('td');
}

function esc(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}
