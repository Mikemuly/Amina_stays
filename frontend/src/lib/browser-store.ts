/**
 * A minimal external store for React.useSyncExternalStore over localStorage: `notify` re-renders this tab's
 * subscribers and changes made in other tabs arrive through the `storage` event.
 */
export function createBrowserStore<T>(read: () => T) {
  const listeners = new Set<() => void>();
  return {
    read,
    subscribe(cb: () => void) {
      listeners.add(cb);
      window.addEventListener("storage", cb);
      return () => {
        listeners.delete(cb);
        window.removeEventListener("storage", cb);
      };
    },
    notify: () => listeners.forEach((l) => l()),
  };
}

// Storage can be blocked (privacy settings, some embedded browsers); preferences then simply don't persist.
export function readStorage(key: string) {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writeStorage(key: string, value: string) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // ignored: see above
  }
}
