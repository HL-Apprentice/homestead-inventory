import QRCode from 'qrcode';

/**
 * UTF-8-safe base64. Plain btoa() throws on any character outside Latin1
 * (accents like "Café", "Piñata", emoji, CJK, Cyrillic), which room/cupboard
 * names can contain. Encoding via UTF-8 bytes first makes it safe for any name,
 * and is byte-identical to btoa() for ASCII so existing QR codes still decode.
 */
export function utf8ToBase64(str: string): string {
  const bytes = new TextEncoder().encode(str);
  let binary = '';
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary);
}

/** Inverse of utf8ToBase64 — decode a base64 payload back to a string.
 *
 * New QR codes hold UTF-8 bytes. Legacy codes were plain `btoa(str)` of a
 * Latin-1 string (which only failed for chars > 0xFF), so accented names like
 * "Café" produced valid-but-non-UTF-8 bytes. Decoding UTF-8 strictly and
 * falling back to the raw Latin-1 binary makes both old and new codes decode
 * correctly. */
export function base64ToUtf8(b64: string): string {
  const binary = atob(b64);
  const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(bytes);
  } catch {
    return binary; // legacy Latin-1 payload
  }
}

/**
 * Build the deep link a QR code points at. Scanning it opens the Homestead
 * Inventory panel navigated straight to this room/cupboard so you can add
 * items to that physical location. App.tsx decodes the `data` param on load.
 */
export function buildDeepLink(room: string, cupboard: string): string {
  const payload = JSON.stringify({ room, cupboard });
  return `homeassistant://navigate/homestead_inventory?data=${utf8ToBase64(
    payload
  )}`;
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

/** Make a name safe for use in a download filename (no slashes, etc.). */
function safeFilePart(s: string): string {
  return (s || '').replace(/[^a-zA-Z0-9 _-]/g, '_').slice(0, 60) || 'location';
}

export async function downloadQRCode(room: string, cupboard: string): Promise<void> {
  const dataUrl = await generateQRCodeDataUrl(room, cupboard);

  const link = document.createElement('a');
  link.href = dataUrl;
  link.download = `QR_${safeFilePart(room)}_${safeFilePart(cupboard)}.png`;

  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}
