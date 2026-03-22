export interface DiskInfo {
  raw: string;
  size_value: number | null;
  size_unit: string | null;
  label: string | null;
}

export interface LocationInfo {
  raw: string;
  normalized: string;
  test_ip: string | null;
}

export interface ServerSpecs {
  cpu: string | null;
  memory: string | null;
  disks: DiskInfo[];
  monthly_transfer: string | null;
  public_network_port: string | null;
  raw_lines: string[];
}

export interface ServerInfo {
  category_name: string;
  store_title: string;
  model: string;
  product_url: string;
  confproduct_url: string;
  pid: number | null;
  store_price_cycle: string | null;
  billing_cycle_annually_usd: number;
  raw_locations: string[];
  normalized_locations: string[];
  location_options: LocationInfo[];
  specs: ServerSpecs;
  updated_at: string;
  store_card_text: string | null;
}

export interface SnapshotFile {
  updated_at: string;
  source_categories: string[];
  item_count: number;
  items: ServerInfo[];
}

export interface ServerRow extends ServerInfo {
  supportsDc02: boolean;
  supportsDc03: boolean;
  display_memory: string;
  display_disk: string;
  display_bandwidth: string;
  locations_label: string;
  updated_at_label: string;
  price_label: string;
  search_blob: string;
}

export interface SnapshotView {
  rows: ServerRow[];
  categoryOptions: string[];
  locationOptions: string[];
  summary: {
    updatedAtLabel: string;
    itemCount: number;
    categoryCount: number;
    dc02Count: number;
    dc03Count: number;
  };
}

export async function loadSnapshot(url: string): Promise<SnapshotFile> {
  const response = await fetch(url, {
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`请求失败：${response.status} ${response.statusText}`);
  }

  const payload: unknown = await response.json();
  return parseSnapshotFile(payload);
}

export function parseSnapshotFile(payload: unknown): SnapshotFile {
  const root = asObject(payload, 'snapshot');
  const updatedAt = asString(root.updated_at, 'updated_at');
  const sourceCategories = asStringArray(root.source_categories, 'source_categories');
  const itemCount = asNumber(root.item_count, 'item_count');
  const items = asArray(root.items, 'items').map((item, index) => parseServerInfo(item, index));

  return {
    updated_at: updatedAt,
    source_categories: sourceCategories,
    item_count: itemCount,
    items,
  };
}

export function deriveSnapshotView(snapshot: SnapshotFile): SnapshotView {
  const rows = snapshot.items.map((item) => deriveServerRow(item, snapshot.updated_at));
  const categoryOptions = uniqueValues(rows.map((row) => row.category_name));
  const locationOptions = uniqueValues(rows.flatMap((row) => row.normalized_locations));

  return {
    rows,
    categoryOptions,
    locationOptions,
    summary: {
      updatedAtLabel: formatDateTime(snapshot.updated_at),
      itemCount: rows.length,
      categoryCount: categoryOptions.length,
      dc02Count: rows.filter((row) => row.supportsDc02).length,
      dc03Count: rows.filter((row) => row.supportsDc03).length,
    },
  };
}

export function detectDcSupport(locations: string[], code: 'DC02' | 'DC03'): boolean {
  const token = code.toUpperCase().replaceAll('-', '');
  return locations.some((location) =>
    location.toUpperCase().replaceAll(/\s|-/g, '').includes(token),
  );
}

export function buildStateMessage(
  kind: 'loading' | 'error' | 'empty',
  detail?: string,
): {
  title: string;
  description: string;
} {
  if (kind === 'loading') {
    return {
      title: '正在加载数据',
      description: '准备读取 <code>data/latest.json</code> 并初始化库存表格。',
    };
  }

  if (kind === 'empty') {
    return {
      title: '当前没有可展示的套餐',
      description: 'JSON 已成功读取，但 <code>items</code> 为空，请等待下一次抓取结果。',
    };
  }

  return {
    title: '数据加载失败',
    description: detail ?? '读取 <code>data/latest.json</code> 时发生错误，请稍后再试。',
  };
}

export function formatUsd(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function formatBandwidth(raw: string | null): string {
  if (raw === null) return '--';
  const match = raw.match(/([\d,]+)\s*GB/i);
  if (!match) return raw;
  const gb = parseInt(match[1].replaceAll(',', ''), 10);
  if (gb >= 1024) {
    const tb = Math.round(gb / 1024);
    return raw.replace(match[0], `${tb}TB`);
  }
  return raw;
}

function deriveServerRow(item: ServerInfo, snapshotUpdatedAt: string): ServerRow {
  const supportsDc02 = detectDcSupport(item.normalized_locations, 'DC02');
  const supportsDc03 = detectDcSupport(item.normalized_locations, 'DC03');
  const displayDisk =
    item.specs.disks.length > 0 ? item.specs.disks.map((disk) => disk.raw).join(' + ') : '--';
  const displayMemory = item.specs.memory ?? '--';
  const displayBandwidth = formatBandwidth(item.specs.monthly_transfer);
  const updatedAtIso = item.updated_at || snapshotUpdatedAt;
  const locationsLabel = item.normalized_locations.join(' / ');

  return {
    ...item,
    supportsDc02,
    supportsDc03,
    display_memory: displayMemory,
    display_disk: displayDisk,
    display_bandwidth: displayBandwidth,
    locations_label: locationsLabel,
    updated_at_label: formatDateTime(updatedAtIso),
    price_label: formatUsd(item.billing_cycle_annually_usd),
    search_blob: [
      item.store_title,
      item.model,
      item.category_name,
      locationsLabel,
      displayMemory,
      displayDisk,
      displayBandwidth,
      item.specs.cpu ?? '',
      item.specs.public_network_port ?? '',
    ]
      .join(' ')
      .toLowerCase(),
  };
}

function parseServerInfo(payload: unknown, index: number): ServerInfo {
  const item = asObject(payload, `items[${index}]`);
  return {
    category_name: asString(item.category_name, 'category_name'),
    store_title: asString(item.store_title, 'store_title'),
    model: asString(item.model, 'model'),
    product_url: asString(item.product_url, 'product_url'),
    confproduct_url: asString(item.confproduct_url, 'confproduct_url'),
    pid: asOptionalNumber(item.pid) ?? 0,
    store_price_cycle: asOptionalString(item.store_price_cycle),
    billing_cycle_annually_usd: asNumber(item.billing_cycle_annually_usd, 'billing_cycle_annually_usd'),
    raw_locations: asStringArray(item.raw_locations, 'raw_locations'),
    normalized_locations: asStringArray(item.normalized_locations, 'normalized_locations'),
    location_options: asArray(item.location_options, 'location_options').map((option, optionIndex) =>
      parseLocationInfo(option, optionIndex),
    ),
    specs: parseServerSpecs(item.specs),
    updated_at: asString(item.updated_at, 'updated_at'),
    store_card_text: asOptionalString(item.store_card_text),
  };
}

function parseLocationInfo(payload: unknown, index: number): LocationInfo {
  const item = asObject(payload, `location_options[${index}]`);
  return {
    raw: asString(item.raw, 'raw'),
    normalized: asString(item.normalized, 'normalized'),
    test_ip: asOptionalString(item.test_ip),
  };
}

function parseServerSpecs(payload: unknown): ServerSpecs {
  const specs = asObject(payload, 'specs');
  return {
    cpu: asOptionalString(specs.cpu),
    memory: asOptionalString(specs.memory),
    disks: asArray(specs.disks, 'disks').map((disk, index) => parseDiskInfo(disk, index)),
    monthly_transfer: asOptionalString(specs.monthly_transfer),
    public_network_port: asOptionalString(specs.public_network_port),
    raw_lines: asStringArray(specs.raw_lines, 'raw_lines'),
  };
}

function parseDiskInfo(payload: unknown, index: number): DiskInfo {
  const disk = asObject(payload, `disks[${index}]`);
  return {
    raw: asString(disk.raw, 'raw'),
    size_value: asOptionalNumber(disk.size_value),
    size_unit: asOptionalString(disk.size_unit),
    label: asOptionalString(disk.label),
  };
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

function uniqueValues(values: string[]): string[] {
  return [...new Set(values)].sort((left, right) => left.localeCompare(right, 'zh-CN'));
}

function asObject(value: unknown, fieldName: string): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new Error(`${fieldName} 不是对象`);
  }

  return value as Record<string, unknown>;
}

function asArray(value: unknown, fieldName: string): unknown[] {
  if (!Array.isArray(value)) {
    throw new Error(`${fieldName} 不是数组`);
  }

  return value;
}

function asString(value: unknown, fieldName: string): string {
  if (typeof value !== 'string') {
    throw new Error(`${fieldName} 不是字符串`);
  }

  return value;
}

function asOptionalString(value: unknown): string | null {
  if (value === null || value === undefined) {
    return null;
  }

  if (typeof value !== 'string') {
    throw new Error('可选字符串字段类型错误');
  }

  return value;
}

function asNumber(value: unknown, fieldName: string): number {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    throw new Error(`${fieldName} 不是数字`);
  }

  return value;
}

function asOptionalNumber(value: unknown): number | null {
  if (value === null || value === undefined) {
    return null;
  }

  if (typeof value !== 'number' || Number.isNaN(value)) {
    throw new Error('可选数字字段类型错误');
  }

  return value;
}

function asStringArray(value: unknown, fieldName: string): string[] {
  return asArray(value, fieldName).map((item, index) => {
    if (typeof item !== 'string') {
      throw new Error(`${fieldName}[${index}] 不是字符串`);
    }
    return item;
  });
}
