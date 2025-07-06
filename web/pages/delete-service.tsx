import { useState } from 'react';
import { apiFetch } from '../lib/api';

export default function DeleteService() {
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleDelete() {
    try {
      const res = await apiFetch('/provision/default', { method: 'DELETE' });
      setStatus(res.status);
    } catch (e: any) {
      setError(e.message);
    }
  }

  return (
    <main style={{ padding: 20 }}>
      <h1>Delete Service</h1>
      {status && <p>{status}</p>}
      {error && <p style={{ color: 'red' }}>{error}</p>}
      <button onClick={handleDelete}>Delete</button>
    </main>
  );
}
