import { useQuery } from '@tanstack/react-query';
import { Modal, ModalHeader } from './Modal';
import type { Item } from '../../types';
import type { ApiService } from '../../services/api';
import { useTranslation } from '../../i18n/I18nContext';

interface HistoryModalProps {
  isOpen: boolean;
  onClose: () => void;
  item: Item;
  api: ApiService;
}

function formatWhen(ts: string): string {
  // The backend stores UTC timestamps as "YYYY-MM-DD HH:MM:SS".
  const iso = ts.includes('T') ? ts : ts.replace(' ', 'T') + 'Z';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return ts;
  return d.toLocaleString();
}

export default function HistoryModal({
  isOpen,
  onClose,
  item,
  api,
}: HistoryModalProps) {
  const { t } = useTranslation();

  const historyQuery = useQuery({
    queryKey: ['item-history', item.id],
    queryFn: () => api.getItemHistory(item.id),
    enabled: isOpen,
  });

  const ratesQuery = useQuery({
    queryKey: ['item-rates', item.id],
    queryFn: () => api.getConsumptionRates(item.id, 30),
    enabled: isOpen,
  });

  const history = historyQuery.data?.history ?? [];
  const rates = ratesQuery.data;
  const hasUsage = !!rates && rates.total_used > 0;

  return (
    <Modal isOpen={isOpen} onClose={onClose}>
      <ModalHeader onClose={onClose}>
        📊 {item.name} — {t.history.title}
      </ModalHeader>

      {/* Analytics */}
      <div className="bg-ha-secondary-bg p-4 rounded-lg mb-4">
        <div className="text-[0.85em] text-ha-text/70 font-medium mb-3">
          {t.history.analytics} ({t.history.window})
        </div>
        {ratesQuery.isLoading ? (
          <div className="text-sm text-ha-text/70">{t.history.loading}</div>
        ) : hasUsage ? (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label={t.history.perDay} value={rates!.daily_rate} />
            <Stat label={t.history.perWeek} value={rates!.weekly_rate} />
            <Stat
              label={t.history.totalUsed}
              value={rates!.total_used}
            />
            <Stat
              label={t.history.daysLeft}
              value={rates!.days_left ?? '∞'}
            />
          </div>
        ) : (
          <div className="text-sm text-ha-text/70">
            {t.history.notEnoughData}
          </div>
        )}
      </div>

      {/* Timeline */}
      <div className="bg-ha-secondary-bg p-4 rounded-lg">
        <div className="text-[0.85em] text-ha-text/70 font-medium mb-3">
          🕒 {t.history.title}
        </div>
        {historyQuery.isLoading ? (
          <div className="text-sm text-ha-text/70">{t.history.loading}</div>
        ) : historyQuery.isError ? (
          <div className="text-sm text-ha-error">{t.history.error}</div>
        ) : history.length === 0 ? (
          <div className="text-sm text-ha-text/70">{t.history.noHistory}</div>
        ) : (
          <ul className="space-y-2 max-h-[16rem] overflow-y-auto">
            {history.map((h, i) => {
              const up = h.delta > 0;
              return (
                <li
                  key={i}
                  className="flex items-center justify-between gap-3 text-sm border-b border-ha-divider/50 pb-2 last:border-0 last:pb-0"
                >
                  <div className="flex items-center gap-2">
                    <span
                      className={`font-bold ${
                        up ? 'text-green-500' : 'text-ha-error'
                      }`}
                    >
                      {up ? '+' : ''}
                      {h.delta}
                    </span>
                    <span className="text-ha-text/60">
                      {h.source === 'consume'
                        ? t.history.consumed
                        : t.history.adjusted}
                      {h.quantity_after !== null
                        ? ` → ${h.quantity_after}`
                        : ''}
                    </span>
                  </div>
                  <span className="text-ha-text/50 text-xs whitespace-nowrap">
                    {formatWhen(h.created_at)}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </Modal>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="bg-ha-card p-3 rounded text-center">
      <div className="text-[0.75em] text-ha-text/60 mb-1">{label}</div>
      <div className="text-lg font-bold text-ha-text">{value}</div>
    </div>
  );
}
