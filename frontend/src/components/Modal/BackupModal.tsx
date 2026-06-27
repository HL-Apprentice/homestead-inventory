import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Modal, ModalHeader } from './Modal';
import type { ApiService } from '../../services/api';
import { useTranslation } from '../../i18n/I18nContext';

interface BackupModalProps {
  isOpen: boolean;
  onClose: () => void;
  api: ApiService;
}

type ImportCounts = {
  rooms: number;
  cupboards: number;
  shelves: number;
  organizers: number;
  items: number;
};

export default function BackupModal({ isOpen, onClose, api }: BackupModalProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [replace, setReplace] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ImportCounts | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleExport = async () => {
    setError(null);
    try {
      const data = await api.exportData();
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: 'application/json',
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'homestead-inventory-backup.json';
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setError(t.errors.generalError);
    }
  };

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ''; // allow re-selecting the same file
    if (!file) return;

    setError(null);
    setResult(null);

    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(await file.text());
      if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
        throw new Error('bad');
      }
    } catch {
      setError(t.backup.badFile);
      return;
    }

    if (replace && !window.confirm(t.backup.confirmReplace)) return;

    setBusy(true);
    try {
      const res = await api.importData(parsed, replace);
      setResult(res.imported);
      await queryClient.invalidateQueries();
    } catch {
      setError(t.backup.badFile);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} maxWidth="480px">
      <ModalHeader onClose={onClose}>💾 {t.backup.title}</ModalHeader>

      {/* Export */}
      <div className="bg-ha-secondary-bg p-4 rounded-lg mb-4">
        <div className="font-semibold text-ha-text mb-1">{t.backup.export}</div>
        <div className="text-sm text-ha-text/70 mb-3">{t.backup.exportHint}</div>
        <button
          onClick={handleExport}
          className="px-3 py-2 bg-ha-primary text-white rounded hover:opacity-90 transition"
        >
          ⬇ {t.backup.export}
        </button>
      </div>

      {/* Import */}
      <div className="bg-ha-secondary-bg p-4 rounded-lg">
        <div className="font-semibold text-ha-text mb-1">{t.backup.import}</div>
        <div className="text-sm text-ha-text/70 mb-3">{t.backup.importHint}</div>

        <label className="flex items-start gap-2 mb-3 text-sm text-ha-text cursor-pointer">
          <input
            type="checkbox"
            checked={replace}
            onChange={(e) => setReplace(e.target.checked)}
            className="mt-1"
          />
          <span>
            {t.backup.replace}
            {replace && (
              <span className="block text-ha-error text-xs mt-1">
                ⚠️ {t.backup.replaceWarning}
              </span>
            )}
          </span>
        </label>

        <label className="inline-block px-3 py-2 bg-ha-card border border-ha-divider text-ha-text rounded hover:bg-ha-secondary-bg transition cursor-pointer">
          {busy ? t.backup.importing : `⬆ ${t.backup.chooseFile}`}
          <input
            type="file"
            accept="application/json,.json"
            onChange={handleFile}
            disabled={busy}
            className="hidden"
          />
        </label>

        {result && (
          <div className="mt-3 text-sm text-green-500">
            ✅ {t.backup.done}: {result.items} items, {result.rooms} rooms,{' '}
            {result.cupboards} cupboards, {result.shelves} shelves,{' '}
            {result.organizers} organizers.
          </div>
        )}
        {error && <div className="mt-3 text-sm text-ha-error">{error}</div>}
      </div>
    </Modal>
  );
}
