import { useEffect, useState } from 'react';
import { apiFetch } from '../lib/api';

interface Login {
  user: string;
  ip: string;
  timestamp: string;
}

export default function LoginHistory() {
  const [history, setHistory] = useState<Login[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch('/history/default')
      .then(setHistory)
      .catch((err) => setError(err.message));
  }, []);

  return (
    <main style={{ padding: 20 }}>
      <h1>Login History</h1>
      {error && <p style={{ color: 'red' }}>{error}</p>}
      <ul>
        {history.map((item, i) => (
          <li key={i}>
            {item.user} from {item.ip} at {item.timestamp}
          </li>
        ))}
      </ul>
    </main>
  );
}
