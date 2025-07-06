import { useState } from 'react';
import { apiFetch } from '../lib/api';

export default function RotateKey() {
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleRotate() {
    try {
      const res = await apiFetch('/rotate-key/default', { method: 'POST' });
      setStatus(res.status);
    } catch (e: any) {
      setError(e.message);
    }
  }

  return (
    <main style={{ padding: 20 }}>
      <h1>Rotate SSH Key</h1>
      {status && <p>{status}</p>}
      {error && <p style={{ color: 'red' }}>{error}</p>}
      <button onClick={handleRotate}>Rotate Key</button>
    </main>
  );
}
