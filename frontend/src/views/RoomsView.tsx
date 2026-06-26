import RoomsHeader from '../components/Room/RoomsHeader';
import RoomCard from '../components/Room/RoomCard';
import { useRooms } from '../hooks/rooms/useRooms';
import { useRoomMutations } from '../hooks/rooms/useRoomMutations';
import { useHomesteadConfig } from '../hooks/global/useHomesteadConfig';
import { useRoomNavigation } from '../hooks/rooms/useRoomNavigation';
import EditRoomModal from '../components/Modal/EditRoomModal';
import ScannerModal from '../components/Modal/ScannerModal';
import { useState } from 'react';
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

  const [showAddModal, setShowAddModal] = useState(false);
  const [roomToEdit, setRoomToEdit] = useState<Room | null>(null);
  const [showScanner, setShowScanner] = useState(false);

  const handleScanFind = async (code: string) => {
    setShowScanner(false);
    try {
      const item = await api.findItemByBarcode(code);
      const s = useAppStore.getState();
      s.setSelectedRoom(item.room ?? null);
      s.setSelectedCupboard(item.cupboard ?? null);
      s.setSelectedShelf(item.shelf ?? null);
      s.setSelectedOrganizer(item.organizer ?? null);
      s.setView('items');
    } catch {
      alert(`No item found for barcode "${code}".`);
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
        onScan={() => setShowScanner(true)}
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
        onDetect={handleScanFind}
        title="Scan to find an item"
      />
    </div>
  );
}
