import RoomsHeader from '../components/Room/RoomsHeader';
import RoomCard from '../components/Room/RoomCard';
import { useRooms } from '../hooks/rooms/useRooms';
import { useRoomMutations } from '../hooks/rooms/useRoomMutations';
import { useHomesteadConfig } from '../hooks/global/useHomesteadConfig';
import { useRoomNavigation } from '../hooks/rooms/useRoomNavigation';
import EditRoomModal from '../components/Modal/EditRoomModal';
import ScannerModal from '../components/Modal/LazyScanner';
import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useAppStore } from '../store/useAppStore';
import type { ApiService } from '../services/api';
import type { Room } from '../types';
import { useTranslation } from '../i18n/I18nContext';

export default function RoomsView({ api }: { api: ApiService }) {
  const { data: rooms = [], isLoading, error } = useRooms(api);
  const { t } = useTranslation();
  const { data: config } = useHomesteadConfig(api);
  const { goToRoom, goToAllItems, goToTrackedItems } = useRoomNavigation();
  const { addRoom, updateRoom } = useRoomMutations(api);
  const queryClient = useQueryClient();

  const [showAddModal, setShowAddModal] = useState(false);
  const [roomToEdit, setRoomToEdit] = useState<Room | null>(null);
  const [showScanner, setShowScanner] = useState(false);
  const [scanMode, setScanMode] = useState<'find' | 'consume'>('find');

  const handleScanFind = async (code: string) => {
    const item = await api.findItemByBarcode(code);
    const s = useAppStore.getState();
    s.setSelectedRoom(item.room ?? null);
    s.setSelectedCupboard(item.cupboard ?? null);
    s.setSelectedShelf(item.shelf ?? null);
    s.setSelectedOrganizer(item.organizer ?? null);
    s.setView('items');
  };

  const handleScanConsume = async (code: string) => {
    const item = await api.findItemByBarcode(code);
    if (!item.track_quantity) {
      alert(`"${item.name}" ${t.scan.notTracked}`);
      return;
    }
    if (item.quantity !== null && item.quantity <= 0) {
      alert(`"${item.name}" ${t.scan.outOfStock}`);
      return;
    }
    const res = await api.consumeItem(item.id);
    await queryClient.invalidateQueries();
    alert(`${t.scan.usedOne} "${res.name}" — ${res.new_quantity} left.`);
  };

  const handleDetect = async (code: string) => {
    setShowScanner(false);
    try {
      if (scanMode === 'consume') {
        await handleScanConsume(code);
      } else {
        await handleScanFind(code);
      }
    } catch {
      alert(`${t.scan.notFound} "${code}".`);
    }
  };

  if (isLoading) return <div className="text-ha-text">{t.common.loading}</div>;
  if (error)
    return <div className="text-ha-error">{t.errors.getRoomsError}</div>;

  return (
    <div className="space-y-4">
      <RoomsHeader
        allowEdit={config?.allow_structure_modification}
        onTrackStock={goToTrackedItems}
        onAllItemsClick={goToAllItems}
        onAddRoom={() => setShowAddModal(true)}
        onScan={() => {
          setScanMode('find');
          setShowScanner(true);
        }}
        onScanConsume={() => {
          setScanMode('consume');
          setShowScanner(true);
        }}
      />

      <div className="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(250px,1fr))]">
        {rooms.length === 0 ? (
          <p className="text-center text-ha-text py-10">
            {t.rooms.noExist}
            {config?.allow_structure_modification && ` ${t.rooms.addFirst}`}
          </p>
        ) : (
          rooms.map((room) => (
            <RoomCard
              key={room.id}
              name={room.name}
              count={room.itemCount}
              editable={config?.allow_structure_modification}
              onClick={() => goToRoom(room.name)}
              onEdit={() => setRoomToEdit(room)}
            />
          ))
        )}
      </div>

      {showAddModal && (
        <EditRoomModal
          room={null}
          isOpen={true}
          currentName=""
          onClose={() => setShowAddModal(false)}
          onSave={async (name) => {
            await addRoom.mutateAsync(name);
            setShowAddModal(false);
          }}
        />
      )}

      {roomToEdit && (
        <EditRoomModal
          room={roomToEdit}
          isOpen={true}
          currentName={roomToEdit.name}
          onClose={() => setRoomToEdit(null)}
          onSave={async (newName) => {
            await updateRoom.mutateAsync({ id: roomToEdit.id, name: newName });
            setRoomToEdit(null);
          }}
        />
      )}

      <ScannerModal
        isOpen={showScanner}
        onClose={() => setShowScanner(false)}
        onDetect={handleDetect}
        title={
          scanMode === 'consume'
            ? 'Scan to use one'
            : 'Scan to find an item'
        }
      />
    </div>
  );
}
