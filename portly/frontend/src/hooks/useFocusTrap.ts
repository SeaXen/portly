import { useEffect, useRef } from "react";
const FOCUSABLE_SELECTOR =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

// Overlays live inside #portly-app-root, so we cannot inert the root itself.
// Inert only background siblings at each level between the dialog and the root.
const inertCounts = new Map<Element, number>();

function backgroundElements(container: HTMLElement | null): HTMLElement[] {
  const root = document.getElementById("portly-app-root");
  if (!root || !container || !root.contains(container)) return [];
  const result: HTMLElement[] = [];
  let current: Element = container;
  while (current && current !== root) {
    const parent = current.parentElement;
    if (!parent) break;
    for (const sibling of Array.from(parent.children)) {
      if (sibling !== current && sibling instanceof HTMLElement) {
        result.push(sibling);
      }
    }
    current = parent;
  }
  return result;
}

function changeInert(elements: HTMLElement[], delta: number) {
  for (const el of elements) {
    const next = (inertCounts.get(el) ?? 0) + delta;
    if (next <= 0) {
      inertCounts.delete(el);
      el.removeAttribute("inert");
      el.removeAttribute("aria-hidden");
    } else {
      inertCounts.set(el, next);
      el.setAttribute("inert", "");
      el.setAttribute("aria-hidden", "true");
    }
  }
}

export function useFocusTrap<T extends HTMLElement = HTMLDivElement>(
  isOpen: boolean,
  onClose?: () => void
) {
  const containerRef = useRef<T | null>(null);
  const triggerRef = useRef<HTMLElement | null>(null);
  // Keep onClose in a ref: callers pass inline closures, and re-running the
  // effect on every parent render would steal focus mid-typing (SSE ticks).
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  useEffect(() => {
    if (!isOpen) return;

    const container = containerRef.current;
    // Save previous focus before any background element becomes inert.
    triggerRef.current = document.activeElement as HTMLElement | null;
    const background = backgroundElements(container);
    if (background.length) changeInert(background, 1);

    const cleanupBackground = () => {
      if (background.length) changeInert(background, -1);
      if (triggerRef.current && typeof triggerRef.current.focus === "function") {
        try {
          triggerRef.current.focus();
        } catch {
          // Element might be detached
        }
      }
    };

    if (!container) return cleanupBackground;

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
      if (e.key === "Escape" && onCloseRef.current) {
        e.preventDefault();
        onCloseRef.current();
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
      cleanupBackground();
    };
  }, [isOpen]);
  return containerRef;
}
