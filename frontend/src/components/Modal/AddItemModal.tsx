import { useState } from 'react';
import { Modal, ModalHeader, ModalFooter } from './Modal';
import ScannerModal from './LazyScanner';
import { useTranslation } from '../../i18n/I18nContext';
import { useHomesteadConfig } from '../../hooks/global/useHomesteadConfig';
import type { ApiService } from '../../services/api';

interface AddItemModalProps {
  isOpen: boolean;
  onClose: () => void;
  api: ApiService;
  onSave: (itemData: {
    name: string;
    aliases?: string;
    barcode?: string | null;
    imageFile?: File | null;
    quantity?: number | null;
    min_quantity?: number | null;
    track_quantity: boolean;
  }) => Promise<void>;
  organizerName?: string | null;
}

export default function AddItemModal({
  isOpen,
  onClose,
  api,
  onSave,
  organizerName,
}: AddItemModalProps) {
  const { t } = useTranslation();
  const { data: config } = useHomesteadConfig(api);
  const [name, setName] = useState('');
  const [aliases, setAliases] = useState('');
  const [barcode, setBarcode] = useState('');
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [quantity, setQuantity] = useState<number | null>(null);
  const [minQuantity, setMinQuantity] = useState<number | null>(null);
  const [trackQuantity, setTrackQuantity] = useState(false);
  const [loading, setLoading] = useState(false);
  const [showScanner, setShowScanner] = useState(false);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] || null;
    setImageFile(file);

    if (file) {
      const reader = new FileReader();
      reader.onload = () => setPreview(reader.result as string);
      reader.readAsDataURL(file);
    }
  };

  const handleDetect = async (code: string) => {
    setShowScanner(false);
    setBarcode(code);
    // If product lookup is enabled and no name yet, try to auto-fill it.
    if (config?.enable_barcode_lookup && !name.trim()) {
      try {
        const res = await api.lookupBarcode(code);
        if (res.found && res.name) setName(res.name);
      } catch {
        /* lookup failed/disabled — leave the name for manual entry */
      }
    }
  };

  const handleSave = async () => {
    if (!name.trim()) return;

    setLoading(true);

    let qty: number | null;

    if (trackQuantity) {
      if (quantity === null || quantity < 0) {
        qty = 0;
      } else {
        qty = quantity;
      }
    } else {
      qty = null;
    }

    try {
      await onSave({
        name: name.trim(),
        aliases: aliases.trim() || undefined,
        barcode: barcode.trim() || undefined,
        imageFile,
        quantity: qty,
        min_quantity: trackQuantity ? minQuantity : null,
        track_quantity: trackQuantity,
      });
      onClose();
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <Modal isOpen={isOpen} onClose={onClose} maxWidth="600px">
        <ModalHeader onClose={onClose}>
          {`➕ ${t.common.add} ${
            organizerName
              ? `in ${organizerName}`
              : t.items.addItemWithoutOrganizer
          }`}
        </ModalHeader>

        <div className="space-y-4">
          {/* Name */}
          <div>
            <label className="text-ha-text text-sm block mb-1">
              {t.items.itemName} *
            </label>
            <input
              type="text"
              maxLength={100}
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-3 py-2 border border-ha-divider bg-ha-secondary-bg text-ha-text rounded"
              placeholder={`${t.common.name}`}
            />
          </div>

          {/* Aliases */}
          <div>
            <label className="text-ha-text text-sm block mb-1">
              {t.items.aliases} ({t.common.optional})
            </label>
            <input
              type="text"
              maxLength={255}
              value={aliases}
              onChange={(e) => setAliases(e.target.value)}
              className="w-full px-3 py-2 border border-ha-divider bg-ha-secondary-bg text-ha-text rounded"
              placeholder="e.g. black toner, ink cartridge"
            />
          </div>

          {/* Barcode */}
          <div>
            <label className="text-ha-text text-sm block mb-1">
              Barcode ({t.common.optional})
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                maxLength={64}
                value={barcode}
                onChange={(e) => setBarcode(e.target.value)}
                className="flex-1 px-3 py-2 border border-ha-divider bg-ha-secondary-bg text-ha-text rounded"
                placeholder="e.g. 0123456789012"
              />
              <button
                type="button"
                onClick={() => setShowScanner(true)}
                aria-label="Scan barcode"
                className="px-3 py-2 bg-ha-secondary-bg border border-ha-divider text-ha-text rounded hover:bg-ha-card transition whitespace-nowrap"
              >
                📷 Scan
              </button>
            </div>
          </div>

          {/* Image preview */}
          {preview && (
            <img
              src={preview}
              alt="Preview"
              className="w-full h-[150px] object-cover rounded border border-ha-divider"
            />
          )}

          {/* Image upload */}
          <div>
            <label className="text-ha-text text-sm block mb-1">
              {t.items.image} ({t.common.optional})
            </label>
            <input
              type="file"
              accept="image/*"
              onChange={handleFileChange}
              className="w-full text-ha-text text-sm"
            />
          </div>

          {/* Track Quantity */}
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="track-quantity-add"
              checked={trackQuantity}
              onChange={(e) => setTrackQuantity(e.target.checked)}
              className="w-4 h-4"
            />
            <label htmlFor="track-quantity-add" className="text-ha-text text-sm">
              {t.items.trackQuantity}
            </label>
          </div>

          {/* Quantity fields */}
          {trackQuantity && (
            <div className="flex gap-3">
              <div className="flex-1">
                <label className="text-ha-text text-sm block mb-1">
                  {t.items.quantity} *
                </label>
                <input
                  type="number"
                  min="0"
                  value={quantity ?? ''}
                  onChange={(e) =>
                    setQuantity(e.target.value ? parseInt(e.target.value) : null)
                  }
                  className="w-full px-3 py-2 border border-ha-divider bg-ha-secondary-bg text-ha-text rounded"
                />
              </div>
              <div className="flex-1">
                <label className="text-ha-text text-sm block mb-1">
                  {t.items.minQuantity}
                </label>
                <input
                  type="number"
                  min="0"
                  value={minQuantity ?? ''}
                  onChange={(e) =>
                    setMinQuantity(
                      e.target.value ? parseInt(e.target.value) : null
                    )
                  }
                  className="w-full px-3 py-2 border border-ha-divider bg-ha-secondary-bg text-ha-text rounded"
                />
              </div>
            </div>
          )}
        </div>

        <ModalFooter>
          <button
            onClick={handleSave}
            disabled={loading || !name.trim()}
            className="flex-1 py-2 bg-ha-primary text-white rounded hover:opacity-90 transition disabled:opacity-50"
          >
            {loading ? t.common.saving : `💾 ${t.common.add}`}
          </button>

          <button
            onClick={onClose}
            disabled={loading}
            className="flex-1 py-2 bg-ha-secondary-bg border border-ha-divider text-ha-text rounded hover:bg-ha-card transition"
          >
            {t.common.cancel}
          </button>
        </ModalFooter>
      </Modal>

      <ScannerModal
        isOpen={showScanner}
        onClose={() => setShowScanner(false)}
        onDetect={handleDetect}
        title="Scan item barcode"
      />
    </>
  );
}
