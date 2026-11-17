import { useEffect, useRef } from "react";

const FOCUSABLE_SELECTOR =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function useFocusTrap<T extends HTMLElement = HTMLDivElement>(
  isOpen: boolean,
  onClose?: () => void
) {
  const containerRef = useRef<T | null>(null);
  const triggerRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!isOpen) return;

    // Save previous focus
    triggerRef.current = document.activeElement as HTMLElement | null;

    const container = containerRef.current;
    if (!container) return;

    // Focus first focusable element or container
    const focusables = Array.from(
      container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
    );
    if (focusables.length > 0) {
      focusables[0].focus();
    } else {
      container.setAttribute("tabindex", "-1");
      container.focus();
    }

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && onClose) {
        e.preventDefault();
        onClose();
        return;
      }

      if (e.key !== "Tab") return;

      const currentFocusables = Array.from(
        container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
      ).filter((el) => el.offsetParent !== null); // Visible elements only

      if (currentFocusables.length === 0) {
        e.preventDefault();
        return;
      }

      const firstEl = currentFocusables[0];
      const lastEl = currentFocusables[currentFocusables.length - 1];

      if (e.shiftKey) {
        if (document.activeElement === firstEl || !container.contains(document.activeElement)) {
          e.preventDefault();
          lastEl.focus();
        }
      } else {
        if (document.activeElement === lastEl || !container.contains(document.activeElement)) {
          e.preventDefault();
          firstEl.focus();
        }
      }
    };

    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      if (triggerRef.current && typeof triggerRef.current.focus === "function") {
        try {
          triggerRef.current.focus();
        } catch {
          // Element might be detached
        }
      }
    };
  }, [isOpen, onClose]);

  return containerRef;
}
