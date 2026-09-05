// Pins are scoped to an account and never sent with HTTP requests.
const fallback = new Map<string, string[]>();
function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("kerjapedia-preferences", 1);
    request.onupgradeneeded = () => request.result.createObjectStore("pins");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
    request.onblocked = () => reject(new Error("Preference database blocked"));
  });
}
export async function accountPins(owner: string, toggle?: string): Promise<string[]> {
  const update = (ids: string[]) => toggle
    ? ids.includes(toggle) ? ids.filter(id => id !== toggle) : [...ids, toggle]
    : ids;
  try {
    const database = await openDatabase();
    return await new Promise<string[]>((resolve, reject) => {
      const transaction = database.transaction("pins", toggle ? "readwrite" : "readonly");
      const store = transaction.objectStore("pins");
      const request = store.get(owner);
      let result: string[] = [];
      request.onsuccess = () => {
        result = update(Array.isArray(request.result) ? request.result.filter((id: unknown): id is string => typeof id === "string") : []);
        if (toggle) store.put(result, owner);
      };
      transaction.oncomplete = () => { database.close(); fallback.set(owner, result); resolve(result); };
      transaction.onabort = () => { database.close(); reject(transaction.error); };
      transaction.onerror = () => { database.close(); reject(transaction.error); };
    });
  } catch {
    // Browsers that disallow IndexedDB retain pins only for this page session.
    const result = update(fallback.get(owner) ?? []);
    fallback.set(owner, result);
    return result;
  }
}
