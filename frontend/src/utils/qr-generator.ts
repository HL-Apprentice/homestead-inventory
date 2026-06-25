import QRCode from 'qrcode';

/**
 * Build the deep link a QR code points at. Scanning it opens the Homestead
 * Inventory panel navigated straight to this room/cupboard so you can add
 * items to that physical location. App.tsx decodes the `data` param on load.
 */
export function buildDeepLink(room: string, cupboard: string): string {
  const payload = JSON.stringify({ room, cupboard });
  return `homeassistant://navigate/homestead_inventory?data=${btoa(payload)}`;
}

/**
 * Render the QR locally (no external service) as a PNG data URL.
 * Keeps the integration 100% local — room/cupboard names never leave the box.
 */
export async function generateQRCodeDataUrl(
  room: string,
  cupboard: string
): Promise<string> {
  return QRCode.toDataURL(buildDeepLink(room, cupboard), {
    width: 400,
    margin: 2,
    errorCorrectionLevel: 'M',
  });
}

export async function downloadQRCode(room: string, cupboard: string): Promise<void> {
  const dataUrl = await generateQRCodeDataUrl(room, cupboard);

  const link = document.createElement('a');
  link.href = dataUrl;
  link.download = `QR_${room}_${cupboard}.png`;

  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}
