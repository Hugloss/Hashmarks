import { loadMetrics } from '../api/metrics';
export async function MetricsPanel() { const values = await loadMetrics(); return values.join(','); }
