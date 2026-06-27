export type Language = 'en';

export interface Translations {
  common: {
    loading: string;
    error: string;
    save: string;
    saving: string;
    cancel: string;
    delete: string;
    deleting: string;
    edit: string;
    add: string;
    search: string;
    close: string;
    confirm: string;
    back: string;
    reload: string;
    deleteConfirm: string;
    deleteConfirm2?: string;
    optional: string;
    select: string;
    name: string;
    infoViewPress: string;
    connectingHA: string;
  };
  rooms: {
    title: string;
    room: string;
    addRoom: string;
    roomName: string;
    allItems: string;
    trackedItems: string;
    noExist: string;
    addFirst: string;
    this: string;
    contain: string;
    containItems: string;
    scanFind: string;
    scanUse: string;
  };
  cupboards: {
    title: string;
    cupboard: string;
    addCupboard: string;
    cupboardName: string;
    deleteConfirm: string;
    noCupboards: string;
    addFirst: string;
    example: string;
  };
  shelves: {
    title: string;
    addShelf: string;
    shelf: string;
    shelfName: string;
    deleteConfirm: string;
    noShelves: string;
    addFirst: string;
  };
  organizers: {
    title: string;
    organizer: string;
    addOrganizer: string;
    organizerName: string;
    deleteConfirm: string;
    withoutOrganizer: string;
    noOrganizers: string;
    addFirst: string;
    moveOrganizer: string;
  };
  items: {
    title: string;
    addItem: string;
    addFirst: string;
    addItemWithoutOrganizer: string;
    itemName: string;
    aliases: string;
    quantity: string;
    minQuantity: string;
    trackQuantity: string;
    location: string;
    image: string;
    deleteConfirm: string;
    noItems: string;
    lowStock: string;
    needsRestock: string;
    pieces: string;
    moveItem: string;
    noTrack: string;
    history: string;
  };
  history: {
    title: string;
    noHistory: string;
    analytics: string;
    perDay: string;
    perWeek: string;
    daysLeft: string;
    totalUsed: string;
    changes: string;
    notEnoughData: string;
    window: string;
    consumed: string;
    adjusted: string;
    loading: string;
    error: string;
  };
  scan: {
    usedOne: string;
    notTracked: string;
    outOfStock: string;
    notFound: string;
  };
  trackedItems: {
    title: string;
    loading: string;
    noItems: string;
    noItemsFiltered: string;
    tryModifyFilters: string;
    enableTracking: string;
    all: string;
    belowStock: string;
    ok: string;
    searchPlaceholder: string;
    locationLabel: string;
    quantityLabel: string;
    needsRestockLabel: string;
  };
  errors: {
    connectionError: string;
    uploadFailed: string;
    generalError: string;
    sameLocationOrganizer: string;
    sameLocationItem: string;
    preloadMoveLocation: string;
    getRoomsError: string;
  };
}

export const translations: Record<Language, Translations> = {
  en: {
    common: {
      loading: 'Loading...',
      error: 'Error',
      save: 'Save',
      saving: 'Saving...',
      cancel: 'Cancel',
      delete: 'Delete',
      deleting: 'Removing...',
      edit: 'Edit',
      add: 'Add',
      search: 'Search',
      close: 'Close',
      confirm: 'Confirm',
      back: 'Back',
      reload: 'Reload',
      deleteConfirm: 'Are you sure you want to delete this',
      optional: 'optional',
      select: 'Select',
      name: 'Name',
      infoViewPress: 'Touch longer or right click to edit',
      connectingHA: 'Connecting to Home Assistant...',
    },
    rooms: {
      title: 'Rooms',
      room: 'Room',
      addRoom: 'Add Room',
      roomName: 'Room name',
      allItems: 'All Items',
      trackedItems: 'Tracked Items',
      noExist: "There's no room.",
      addFirst: ' Add first room.',
      this: 'This',
      contain: 'contain',
      containItems: 'items which will be removed',
      scanFind: 'Find',
      scanUse: 'Use 1',
    },
    cupboards: {
      title: 'Cupboards',
      cupboard: 'Cupboard',
      addCupboard: 'Add Cupboard',
      cupboardName: 'Cupboard name',
      deleteConfirm: 'Are you sure you want to delete this cupboard?',
      noCupboards: 'No cupboards.',
      addFirst: 'Add first cupboard.',
      example: 'e.g: Big cupboard',
    },
    shelves: {
      title: 'Shelves',
      shelf: 'Shelf',
      addShelf: 'Add Shelf',
      shelfName: 'Shelf name',
      deleteConfirm: 'Are you sure you want to delete this shelf?',
      noShelves: "There's no shelves",
      addFirst: 'Add first shelf',
    },
    organizers: {
      title: 'Organizers',
      organizer: 'Organizer',
      addOrganizer: 'Add Organizer',
      organizerName: 'Organizer name',
      deleteConfirm: 'Are you sure you want to delete this organizer?',
      withoutOrganizer: 'Without Organizer',
      noOrganizers: "There's no organizers",
      addFirst: 'Add first organizer',
      moveOrganizer: 'Move the organizer',
    },
    items: {
      title: 'Items',
      addItem: 'Add Item',
      addFirst: 'Add first item',
      addItemWithoutOrganizer: 'Item on shelf',
      itemName: 'Item name',
      aliases: 'Aliases',
      quantity: 'Quantity',
      minQuantity: 'Minimum quantity',
      trackQuantity: 'Track quantity',
      location: 'Location',
      image: 'Image',
      deleteConfirm: 'Are you sure you want to delete this item?',
      noItems: 'No items',
      lowStock: 'Low stock',
      needsRestock: 'Needs restock',
      pieces: 'pieces',
      moveItem: 'Move the item',
      noTrack: 'The quantity is not tracked for this item',
      history: 'History',
    },
    history: {
      title: 'History & usage',
      noHistory: 'No quantity changes recorded yet.',
      analytics: 'Usage analytics',
      perDay: 'Per day',
      perWeek: 'Per week',
      daysLeft: 'Est. days left',
      totalUsed: 'Used',
      changes: 'Changes',
      notEnoughData: 'Not enough usage data yet.',
      window: 'last 30 days',
      consumed: 'Consumed',
      adjusted: 'Adjusted',
      loading: 'Loading history...',
      error: 'Could not load history.',
    },
    scan: {
      usedOne: 'Used 1',
      notTracked: 'is not a tracked item.',
      outOfStock: 'is already at 0.',
      notFound: 'No item found for barcode',
    },
    trackedItems: {
      title: 'Tracked Items',
      loading: 'Loading tracked items...',
      noItems: 'No tracked items',
      noItemsFiltered: 'No items found',
      tryModifyFilters: 'Try modifying the filters',
      enableTracking: 'Enable quantity tracking for items',
      all: 'All',
      belowStock: 'Below stock',
      ok: 'OK',
      searchPlaceholder: 'Search items...',
      locationLabel: 'Location:',
      quantityLabel: 'Quantity:',
      needsRestockLabel: 'Needs restock',
    },
    errors: {
      connectionError: 'Connection error',
      uploadFailed: 'Upload failed',
      generalError: 'An error occurred',
      sameLocationOrganizer: 'The organizer is in the same location',
      sameLocationItem: 'The item is in the same location',
      preloadMoveLocation: 'Error at preloaded current location',
      getRoomsError: 'Error at fetching rooms.',
    },
  },
};
