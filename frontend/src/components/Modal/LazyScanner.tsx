import { Component, lazy, Suspense, type ReactNode } from 'react';
import { Modal, ModalHeader } from './Modal';

/**
 * Lazily loads the camera scanner (and its @zxing/browser dependency) only the
 * first time the user actually opens it. Keeping the scanner out of the main
 * panel bundle keeps initial load fast.
 *
 * The error boundary below guarantees the contract: if the scanner chunk fails
 * to load (404 after a partial upgrade, offline, etc.) it degrades to a small
 * "couldn't load" message — it can NEVER take down the rest of the panel.
 */
const ScannerModal = lazy(() => import('./ScannerModal'));

interface LazyScannerProps {
  isOpen: boolean;
  onClose: () => void;
  onDetect: (code: string) => void;
  title?: string;
}

class ScannerBoundary extends Component<
  { onClose: () => void; children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (this.state.failed) {
      return (
        <Modal isOpen={true} onClose={this.props.onClose} maxWidth="480px">
          <ModalHeader onClose={this.props.onClose}>Scanner</ModalHeader>
          <div className="text-ha-text text-sm p-4 text-center leading-relaxed">
            The scanner could not be loaded. Reload the page and try again, or
            type the barcode in manually.
          </div>
        </Modal>
      );
    }
    return this.props.children;
  }
}

export default function LazyScanner(props: LazyScannerProps) {
  // Returning null while closed means the lazy import is not requested until
  // the user opens the scanner for the first time.
  if (!props.isOpen) return null;
  return (
    <ScannerBoundary onClose={props.onClose}>
      <Suspense fallback={null}>
        <ScannerModal {...props} />
      </Suspense>
    </ScannerBoundary>
  );
}
