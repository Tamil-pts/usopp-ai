/** Browser preferences and saved input selections belong to the signed-in account. */
let accountId: string | null = null;
const keyFor = (key: string) => `usopp-user:${accountId || 'signed-out'}:${key}`;

export function activateUserStorage(user: {id: number; role?: string} | null) {
  accountId = user ? String(user.id) : null;
  // The earlier single-user browser state is adopted only by Admin once.
  if (user?.role === 'admin' && !window.localStorage.getItem(keyFor('storage-migrated-v1'))) {
    const keys = Object.keys(window.localStorage).filter(key => /^(usopp_|spinning_|spinconnect_|plc_configs$|nami_)/.test(key));
    for (const key of keys) {
      if (window.localStorage.getItem(keyFor(key)) === null) {
        const value = window.localStorage.getItem(key);
        if (value !== null) window.localStorage.setItem(keyFor(key), value);
      }
    }
    window.localStorage.setItem(keyFor('storage-migrated-v1'), '1');
  }
}

export const userStorage = {
  getItem: (key: string) => window.localStorage.getItem(keyFor(key)),
  setItem: (key: string, value: string) => window.localStorage.setItem(keyFor(key), value),
  removeItem: (key: string) => window.localStorage.removeItem(keyFor(key)),
  clear: () => {
    const prefix = keyFor('');
    Object.keys(window.localStorage).filter(key => key.startsWith(prefix)).forEach(key => window.localStorage.removeItem(key));
  },
};
