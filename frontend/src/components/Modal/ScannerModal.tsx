import { useEffect, useRef } from 'react';
import {
  BrowserMultiFormatReader,
  type IScannerControls,
} from '@zxing/browser';
import { Modal, ModalHeader } from './Modal';

interface ScannerModalProps {
  isOpen: boolean;
  onClose: () => void;
  onDetect: (code: string) => void;
  title?: string;
}

/**
 * Camera barcode/QR scanner. Uses @zxing/browser, which decodes from a
 * <video> element we pass by ref — so it works inside the panel's shadow DOM
 * (unlike libraries that call document.getElementById).
 *
 * getUserMedia requires a secure context (HTTPS or localhost). Over plain HTTP
 * the browser blocks the camera, so we show guidance and fall back to manual
 * barcode entry instead of failing silently.
 */
export default function ScannerModal({
  isOpen,
  onClose,
  onDetect,
  title,
}: ScannerModalProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const secure =
    typeof window !== 'undefined' && window.isSecureContext === true;

  useEffect(() => {
    if (!isOpen || !secure) return;
    const video = videoRef.current;
    if (!video) return;

    let stopped = false;
    let controls: IScannerControls | null = null;
    const reader = new BrowserMultiFormatReader();

    reader
      .decodeFromVideoDevice(undefined, video, (result, _err, c) => {
        controls = c;
        if (stopped) {
          c.stop();
          return;
        }
        if (result) {
          stopped = true;
          c.stop();
          onDetect(result.getText());
        }
      })
      .then((c) => {
        controls = c;
        if (stopped) c.stop();
      })
      .catch(() => {
        /* camera denied or unavailable — handled by the UI */
      });

    return () => {
      stopped = true;
      controls?.stop();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, secure]);

  if (!isOpen) return null;

  return (
    <Modal isOpen={isOpen} onClose={onClose} maxWidth="480px">
      <ModalHeader onClose={onClose}>{title || 'Scan barcode'}</ModalHeader>
      {secure ? (
        <>
          <video
            ref={videoRef}
            className="w-full rounded bg-black aspect-[4/3] object-cover"
            muted
            playsInline
          />
          <p className="text-ha-text/70 text-xs text-center mt-2">
            Point the camera at a barcode or QR code.
          </p>
        </>
      ) : (
        <div className="text-ha-text text-sm p-4 text-center leading-relaxed">
          Camera scanning needs a secure (HTTPS) connection. Open Home Assistant
          over HTTPS or via the Companion app — or just type the barcode in
          manually.
        </div>
      )}
    </Modal>
  );
}
